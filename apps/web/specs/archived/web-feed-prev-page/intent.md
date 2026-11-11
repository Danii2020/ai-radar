# Intent: Web Feed Previous Page

Revision: 1
Approval: Approved revision 1 on 2026-11-10 under the human's standing instruction to run fully autonomously and auto-accept every gate (recorded by the conductor, not by the architect). The drain-direction decision (`dir=prev` URL hint) and the no-CSS-change layout default were accepted by the conductor under that instruction.

Shipped: 2026-11-10

## Outcome
The web feed gets a `‹ Previous page` link next to `← First page` and `Next page →`, above and below the
cards. It uses the `prev_cursor` that the deployed `feed-api` now returns (FA-7), passed back byte for byte
through `?cursor=`, so a reader can step back one page without the browser Back button. Empty filtered pages
met while going back are drained backward, so Previous never bounces the reader forward and never skips a card.

## Acceptance criteria

Notation: "page P1" and "page P2" are the stub's first and second unfiltered pages. "Following" a link means
clicking it in the rendered feed. `<prev>` and `<next>` are the `prev_cursor` and `next_cursor` of the page on
screen.

- **AC1** A `‹ Previous page` link is shown if and only if the page on screen has a non-null `prev_cursor`.
  Its href is `/?tag=<t>&cursor=<prev>&dir=prev` (`tag` omitted when there is no filter), with `<prev>` carried
  byte-identical (URL-encoded in transit only). It appears in both pagination bars of the list state and in the
  bar of the no-match state. In each bar the links are in the order `← First page`, `‹ Previous page`,
  `Next page →`.
  Example: page P2 (reached with `?cursor=<N>`, response `prev_cursor: "<P>"`) -> both bars show
  `← First page` -> `/`, `‹ Previous page` -> `/?cursor=<P>&dir=prev`; no `Next page →` (its `next_cursor` is null).

- **AC2** (compatibility) `← First page` and `Next page →` keep their text, hrefs and rules: First only when the
  page was requested with a cursor, Next only when `next_cursor` is non-null, and the Next href never carries
  `dir`. No bar renders when no link applies.
  Example: `/` with `prev_cursor: null`, `next_cursor: "<N>"` -> one link per bar, `Next page →` -> `/?cursor=<N>`.

- **AC3** (compatibility, older backend) A response whose `prev_cursor` is missing, `null`, an empty string or not
  a string is still a valid response: the page renders normally with no `‹ Previous page` link, and no error or
  `feed_fetch_failed` line is produced.
  Example: `{"cards":[c1],"next_cursor":null}` -> list state with c1, no Previous link.

- **AC4** Without a tag filter, following `Next page →` and then `‹ Previous page` shows exactly the cards of the
  first page again, in the same order, and the URL's `cursor` equals the second page's `prev_cursor` with
  `dir=prev`.
  Example: `/` (P1) -> Next -> P2 -> Previous -> URL `/?cursor=<P>&dir=prev`, cards identical to P1, no Previous
  link (P1's backward response has `prev_cursor: null`), `Next page →` present.

- **AC5** A request marked `dir=prev` drains backward. While the page is empty and its `prev_cursor` is non-null,
  the loader follows `prev_cursor` byte-identical, never `next_cursor`, up to `MAX_DRAIN_REQUESTS` (5) requests in
  total. It returns the first non-empty page, or the last empty page with both cursors intact. A request without
  `dir=prev` drains exactly as today (follows `next_cursor`). The web app never decodes a cursor to learn its
  direction.
  Example: `/?tag=x&cursor=<B0>&dir=prev`, responses `[] prev=<B1>`, `[] prev=<B2>`, `[c2] prev=<B3> next=<F>`
  -> three requests with cursors `<B0>`, `<B1>`, `<B2>`; c2 shown; Previous -> `cursor=<B3>&dir=prev`,
  Next -> `cursor=<F>`.

- **AC6** The empty state after a backward drain is honest. It never says "the first N pages". When its
  `prev_cursor` is non-null it says that N pages back were searched without a match and points to the Previous
  link. When its `prev_cursor` is null it says there are no earlier matches and points to the Next link. The
  forward no-match copy is unchanged.
  Example: backward drain capped at 5 empty pages, `prev_cursor: "<B5>"` -> no-match state, copy names 5 pages
  back, `‹ Previous page` -> `cursor=<B5>&dir=prev`.

- **AC7** (compatibility) `dir` is the web app's own URL hint. Only the exact value `prev` together with a
  non-empty `cursor` selects backward draining; any other value, a repeated `dir`, or `dir` without a cursor means
  forward. URLs without `dir` (bookmarks, shared links, old `?cursor=` links) behave exactly as before. `dir` is
  never sent to `feed-api`. The error state's `Try again` link reproduces the same `tag`, `cursor` and `dir`.
  Example: `/?dir=prev` -> the first page, as `/`. `/?tag=network&cursor=abc&dir=prev` -> error state,
  `Try again` -> `/?tag=network&cursor=abc&dir=prev`.

- **AC8** (compatibility) Nothing else changes. The 17 baseline scenarios in `e2e/feed.e2e.ts` match their
  snapshots, except `ok-last-page`, whose DOM gains the Previous link in both bars (an intentional change,
  re-captured and its diff reviewed); no style or console snapshot changes. The barrel still exports exactly
  `FeedView`, `loadFeedState`, `parseFeedSearchParams`. The `feed_fetch_failed` line keeps its keys and order.
  `types.generated.ts` and `feed.module.css` are not edited. `npm run lint`, `typecheck`, `test`, `build` and
  `test:e2e` pass.

- **AC9** (docs) The repo-root `README.md` no longer says the web app does not use `prev_cursor`, the web-app
  browser check in `docs/runbooks.md` includes Previous, and `apps/web/AGENTS.md` WEB-4 names the direction rule.

- **AC10** (local, against the real API) A local dev-server browser check against the deployed `feed-api`
  (16 cards, page size 5): `/` -> Next -> Previous shows the same 5 cards, and the first page shows no Previous
  link. Run by the executor if `FEED_API_BASE_URL` is available locally, otherwise recorded as pending for the
  human (WEB-11).

## Scope
**In**
- Normalizing `prev_cursor` in the fetch client, and a direction-aware drain in the loader.
- A `dir=prev` URL hint parsed with the other search params and threaded to the loader and the view.
- The `‹ Previous page` link in `Pagination`, and the honest backward no-match copy.
- The e2e stub serving `prev_cursor` on the unfiltered second page, one Playwright flow, and the
  `ok-last-page` baseline re-capture.
- The README, runbook and AGENTS.md lines in AC9.

**Out**
- Any backend change (`feed-api` is deployed and live-checked; `types.generated.ts` is already regenerated).
- Aligning filtered backward page boundaries with the forward ones (accepted reservation FA-R2: the executor
  must not compensate, for example by over-fetching or re-querying).
- Any CSS or design-token change, page numbers, a "Last page" link, client-side state or JS navigation.
- Vercel deploy and the `feed-api` CORS origin (human-only, WEB-R1).

## Constraints
- WEB-1: all fetching stays server-side; `components/` and `lib/` keep `import type` only from `api/`.
- WEB-2: `types.generated.ts` is never hand-edited.
- WEB-3 and invariant 2: cursors stay opaque bytes. The direction is never read from a cursor; it comes only
  from the web app's own `dir` URL hint. No `.sort(` or `.reverse(` under `features/`.
- WEB-4: the drain stays bounded by `MAX_DRAIN_REQUESTS` (5) per render, in either direction.
- WEB-5: still exactly one of the four render states.
- WEB-9: no edit to `feed.module.css` or `globals.css`; the new link reuses `.pagerLink` inside `.pagerBar`.
- Invariant 3: `app/page.tsx` stays a thin shell (it passes the parsed direction through, nothing more).
- FA-7 and FA-R2 (root `specs/current/feed-api.md`): `prev_cursor` is null only on the first page; a backward
  page always has a non-null `next_cursor`; filtered backward boundaries may differ from forward ones.
- The uncommitted feed work on `feat/feed-prev-cursor` (PAGE_SIZE 5, the top pager, the regenerated baselines,
  the already-corrected `load-feed.ts` drain comment) is kept, not reverted or redone.
- Test scope is the minimum set in `execution-plan.md` § Validation (human instruction; `high-value-tests`).

**Current-truth notes (`harny-sync` lookup, 2026-11-10)**
- `web-feed` WEB-3 says the cursor sent back equals "the `next_cursor` it was given", and WEB-4 says the drain
  "SHALL follow `next_cursor`". This spec extends both: the cursor may also be a `prev_cursor`, and a `dir=prev`
  request drains along `prev_cursor`. Forward behavior is unchanged. Both requirements need a wording amendment
  at archive time; this is an extension, not a silent contradiction.
- `web-feed` WEB-7 still says "281 distinct tags over 87 cards"; the live table has 16 cards. That text is
  `harny-sync`-owned and should be refreshed at archive time. The `load-feed.ts` "87-card corpus" comment is
  already fixed in the working tree (it now reads 5 x PAGE_SIZE(5) = 25 cards), so no code task remains for it.
- ADR numbers: the next free number is 0055 (root index uses up to 0054; 0049 and 0050 belong to
  `web-chat-visitor-rate-limit`).

## Open questions
- None blocking. One revisable default, recorded for the human: with no CSS change, `.pagerBar`'s
  `justify-content: space-between` spreads three links as left, center, right, and on the last page
  (First and Previous only) Previous sits at the right edge where Next usually is. Grouping First and Previous on
  the left would need a design revision under `specs/web-feed-prev-page/design/` (WEB-9, ADR 0039). Default: ship
  without a CSS change.

## Revision history
- Revision 1 (2026-11-10): first draft.

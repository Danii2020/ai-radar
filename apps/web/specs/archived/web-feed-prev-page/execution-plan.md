# Execution Plan: Web Feed Previous Page

## Guidance consulted
- `apps/web/AGENTS.md` (WEB-1 to WEB-5, WEB-9, barrel rules, validation commands, `high-value-tests`).
- `harny-sync` lookup: `apps/web/specs/current/_index.md`, `apps/web/specs/current/web-feed.md` (WEB-1 to WEB-11,
  invariants 1 to 4, ADRs 0003, 0004, 0008, 0039), root `specs/current/feed-api.md` (FA-3, FA-7, FA-R2).
- Root `specs/archived/feed-prev-cursor/intent.md` (AC1 to AC4) and `execution-plan.md` § Binding constraints
  (the page cursor rule table), read for the backward-page cursor rules the drain decision depends on.
- Code: `features/feed/api/{client,load-feed,load-feed-state}.ts`, `lib/{href,search-params}.ts`,
  `components/{pagination,feed-view}.tsx`, `feed.module.css` (`.pagerBar`, `.pagerLink`), `app/page.tsx`,
  `types.generated.ts` (`FeedResponse.prev_cursor?: PrevCursor`), and their tests.
- E2E: `e2e/feed.e2e.ts` (17 baseline scenarios and the navigation tests), `e2e/stub/feed-api-stub.mjs`,
  `e2e/fixtures/populated.json` (page1 15 cards, page2 3 cards, `next_cursor` `e2e+cur/sor==`).
- Docs that make a claim this changes: root `README.md` line "The web app does not use `prev_cursor` yet",
  `docs/runbooks.md` web browser check, `apps/web/AGENTS.md` WEB-4 line.

## Ownership
- `apps/web/features/feed/` (`api/`, `components/`, `lib/`), `apps/web/app/page.tsx` (one pass-through),
  `apps/web/e2e/` (stub, fixture, `feed.e2e.ts`, the `ok-last-page` baseline).
- Docs: root `README.md`, `docs/runbooks.md`, `apps/web/AGENTS.md`.
- Affected `specs/current` capabilities: `web-feed` (WEB-3 and WEB-4 wording amended at archive time; new
  scenario for Previous). `feed-api` is consumed, not changed.

## Binding constraints
- Cursors are opaque bytes. The loader learns the direction only from the web app's own `dir=prev` URL hint,
  never by decoding, comparing or inspecting a cursor (source: WEB-3, `web-feed` invariant 2).
- The cursor sent to `feed-api` is exactly the `prev_cursor` or `next_cursor` string the API returned; `dir` is
  never forwarded to `feed-api` (source: WEB-3; FA-7 "direction lives inside the opaque cursor").
- Drain direction rule (source: AC5; FA-7; root `feed-prev-cursor` cursor rule table):

  | Request | Drain while the page is empty and ... | Follow |
  |---|---|---|
  | no `cursor`, or `cursor` without `dir=prev` | `next_cursor` is non-null | `next_cursor` |
  | `cursor` with `dir=prev` | `prev_cursor` is non-null | `prev_cursor` |

  Total requests per render stay at most `MAX_DRAIN_REQUESTS` (5) in both rows (WEB-4). The result is the first
  non-empty page or the last empty one, with its `nextCursor` and `prevCursor` intact.
- `prev_cursor` normalization mirrors `next_cursor`'s: a non-empty string is kept as-is; anything else (missing,
  `null`, `""`, a non-string) becomes `null`. It must never make `fetchFeed` throw (source: AC3; older backend).
- Link hrefs: First `/?tag=<t>`; Previous `/?tag=<t>&cursor=<prev>&dir=prev`; Next `/?tag=<t>&cursor=<next>`
  (no `dir`). Built through `feedHref` (URLSearchParams), so values are encoded for transit only. Link texts are
  exactly `← First page`, `‹ Previous page`, `Next page →`; DOM order First, Previous, Next (source: AC1, AC2).
- No edit to `feed.module.css`, `globals.css` or `types.generated.ts` (source: WEB-9, WEB-2).
- The barrel exports are unchanged; `components/` and `lib/` still use only `import type` from `api/`; the
  `feed_fetch_failed` line keeps its keys and order (source: invariant 4, `conventions.test.ts`,
  `load-feed-state.test.ts`, the `stderr` baselines).
- No compensation for FA-R2 (filtered backward boundaries differing from forward ones): no over-fetch, no extra
  query, no client-side merge (source: human instruction; FA-R2).
- Keep the uncommitted working-tree changes on `feat/feed-prev-cursor`; do not revert, reformat or re-capture
  baselines other than `ok-last-page` (source: caller instruction; `e2e/feed.e2e.ts` header).

## Proposed approach
Revisable by the executor if it records why.

- Decision: carry the direction as a web-owned URL hint, `dir=prev`, on the Previous link only; the loader drains
  along the pointer that matches it. Rationale: the web app must know which way to drain an empty page, and the
  cursor is opaque, so the only place the direction can live without parsing a cursor is the app's own URL. It
  keeps pagination plain URL links (ADR 0003): Back, bookmarks and sharing keep working, and absent `dir`
  everything behaves exactly as today. A forged `dir=prev` on a forward cursor only changes which server-issued
  pointer an empty page follows, so it cannot skip a card or cost more than the 5-request cap.
  Why it cannot skip a card: each hop follows a server-issued `prev_cursor`, which returns "the cards before that
  page ... with no card skipped or repeated" (FA-7), and every page hopped over had zero cards. The page shown
  then offers its own `next_cursor`, which "returns the cards after that page with no gap and no repeat" (FA-7),
  so going forward again re-crosses the same empty stretch (drained forward) and reaches the page the reader came
  from.
  Rejected:
  - Drain only ever follows `next_cursor`. On an empty backward page, the backend's `next_cursor` is "forward at
    `LastEvaluatedKey`", the far end of the stretch just read (root `feed-prev-cursor` rule table), so the drain
    turns round and walks forward toward the page the reader left. Previous would land back on, or next to, the
    current page: no card is skipped, but a gap of empty filtered pages can never be crossed backward. A
    navigation trap.
  - Show empty backward pages undrained. Live tag filters at page size 5 on 16 cards produce empty pages often
    (FA-3 scenario, FA-R2), so Previous would regularly show a "no matches" state between two non-empty pages,
    which WEB-4 exists to prevent.
  - Infer the direction from the response. A forward page reached by cursor and a backward page both carry two
    non-null cursors (FA-7), so the response cannot tell them apart.
  - Decode the cursor's direction marker. Forbidden by WEB-3 and invariant 2, and it would couple the web app to
    the backend's private token shape (ADR 0051 keeps it opaque).
  - A `?direction=` sent to `feed-api`. The backend has no such parameter (root `feed-prev-cursor` rejected it).
- Decision: `parseFeedSearchParams` returns a third field, the direction (`'prev'` only for the exact string
  `dir=prev` with a non-empty cursor, otherwise forward). `app/page.tsx` passes it to `loadFeedState` and
  `FeedView`; `loadFeedState` passes it to `loadFeed`. Rationale: the existing parse-then-thread path, so the page
  stays a thin shell (invariant 3). Names are the executor's choice.
- Decision: `FeedPage` gains a required `prevCursor: string | null`, normalized in `fetchFeed` beside
  `nextCursor`. Rationale: one normalization point at the network boundary; required (not optional) so the
  compiler finds every page literal in tests. Rejected: reading `prev_cursor` raw in the view (type erasure, AC3).
- Decision: `Pagination` takes `prevCursor` and renders `‹ Previous page` between First and Next, only when it is
  non-null, reusing `.pagerLink`. No new placeholder elements: the bar's DOM changes only where a Previous link
  appears. Rationale: zero CSS change (WEB-9) and the smallest baseline diff. Known effect: on a last page with
  First and Previous only, `space-between` puts Previous at the right edge (intent open question; a grouped layout
  needs a design revision).
- Decision: the no-match state uses backward copy when the request was backward. Suggested copy (revisable, the
  semantics in AC6 are binding): with a non-null `prevCursor`, heading "No earlier matches found yet", body
  "We searched N pages back for “tag” and found no matches. More may exist further back — use the previous page
  link below."; with a null `prevCursor`, heading "No earlier matches", body "There are no earlier cards tagged
  “tag”. Use the next page link below." Forward copy is unchanged. Rationale: every backward page has a non-null
  `next_cursor` (FA-3 amendment), so today's copy would always say "We searched the first N pages", which is false.
- Decision: the error state's `Try again` href keeps `dir` (AC7), so a retry repeats the same request. `Back to the
  first page` is unchanged.
- Decision: e2e stub. The unfiltered second page (`cursor === fixtures.next_cursor`) returns
  `prev_cursor: fixtures.prev_cursor`; that cursor returns `page1` with `next_cursor: fixtures.next_cursor` and
  `prev_cursor: null`. Add `prev_cursor` to `populated.json` with special characters (suggested `e2e+prev/cursor==`)
  so byte-identity through the URL is exercised. All other stub responses stay without `prev_cursor`, which keeps
  their baselines unchanged and exercises AC3 end to end. The stub stays a pure function of (prefix, tag, cursor).
- ADR candidate (0055, written by `harny-adr` if accepted): "The drain direction is a web-owned `dir=prev` URL
  hint, never read from the opaque cursor." Amends the wording of ADR 0004 (drain follows `next_cursor`) for
  backward requests.

## Consumers and migration
- `app/page.tsx`: pass the parsed direction to `loadFeedState` and `FeedView`.
- `FeedPage` literals and helpers in tests gain `prevCursor`: `load-feed.test.ts` (`emptyPage`, `nonEmptyPage`),
  `load-feed-state.test.ts` (`PAGE`), `feed-view.test.tsx` (`okPage`). `load-feed-state.test.ts` assertions on the
  `loadFeed` call arguments, if any, include the direction.
- `lib/search-params.test.ts`: its `toEqual({tag, cursor})` expectations gain the direction field (forward).
- `lib/href.test.ts`: unchanged (the `dir` parameter is optional).
- `e2e/feed.e2e.ts`: update the header line to record the 2026-11-10 Previous-link re-capture; the existing
  navigation test (`Next page carries next_cursor byte-identical; First page and Back work`) must still pass as is.
- `e2e/__baseline__/dom/ok-last-page.html`: re-captured; review the diff (only the added Previous links).
- Docs: root `README.md` (replace "The web app does not use `prev_cursor` yet (a follow-up `apps/web` spec)" with
  a one-line note that the web feed's Previous link uses it, `web-feed-prev-page`); `docs/runbooks.md` web browser
  check (add "Next then Previous shows the same cards"); `apps/web/AGENTS.md` WEB-4 line (a `dir=prev` request
  drains along `prev_cursor`). Specs-current, CHANGELOG and `docs/history.md` are the documenter's and `harny-sync`'s.
- Already done, no task: the `load-feed.ts` "87-card corpus" comment (working tree now reads
  `5 x PAGE_SIZE(5) = 25 cards`). `web-feed.md` WEB-7's "87 cards" is for `harny-sync` at archive time.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A backward drain follows `next_cursor` by mistake and bounces the reader forward | Med | High | Required unit test asserts the hop cursors are the `prevCursor`s, verbatim (AC5) |
| Baseline re-capture hides an unintended DOM change | Low | Med | Re-capture only `ok-last-page`; all 16 others must pass unchanged; review the diff |
| An older backend (no `prev_cursor`) makes pages error | Low | High | Normalization never throws; unit test for missing, null, empty (AC3) |
| `space-between` layout looks odd on the last page | Med | Low | Recorded as a revisable default; a design revision is the path to change it |
| Next Data Cache serves a forward-drained page for a backward URL | Low | Med | The cache keys on the `feed-api` URL, which is per cursor; each hop's cursor is distinct, and `dir` only changes which hop is fetched |

## Validation
Minimum high-value set (human instruction, `high-value-tests`). Each test is new unless marked; nothing restates a
constant, tests a framework, or greps source.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1, AC2 | `FeedView` renders the right links for first page, middle page and "cursor but no prev" | `feed-view.test.tsx`, one test in "FeedView pagination": (a) no cursor, `prevCursor` null -> no First, no Previous, Next present; (b) cursor, `prevCursor` `"a+b/c="`, `nextCursor` set -> First, Previous, Next in that order in both bars, Previous href `/?cursor=a%2Bb%2Fc%3D&dir=prev`, Next href without `dir`; (c) cursor, `prevCursor` null -> First, no Previous. Catches a wrong visibility condition, a swapped cursor, a missing `dir`. Existing T25 and the "above and below" test stay as they are | unit (component) | vitest + Testing Library | `okPage` gains `prevCursor` | `npx vitest run features/feed/components/feed-view.test.tsx` | `npm test` | `apps/web` |
| AC3 | `fetchFeed` normalizes `prev_cursor` | `client.test.ts`, extend the "next_cursor normalisation" block with one `it.each`: a string `prev_cursor` is kept byte-identical; missing, `null`, `""`, `42` give `prevCursor === null` and the call resolves. Catches a throw or a dropped token on the network boundary | unit | vitest | none | `npx vitest run features/feed/api/client.test.ts` | `npm test` | `apps/web` |
| AC5 | Backward drain follows `prevCursor` verbatim, bounded | `load-feed.test.ts`, one test: direction backward, mocked pages `[] prev=B1 next=F1`, `[] prev=B2 next=F2`, `[c] ...` -> `fetchFeed` called with cursors `B0`, `B1`, `B2` (never `F1`/`F2`) and the non-empty page returned; and an all-empty backward run stops at `MAX_DRAIN_REQUESTS` calls with the last `prevCursor` intact. Forward drain stays covered by existing T14 to T17, unchanged | unit | vitest | page helpers gain `prevCursor` | `npx vitest run features/feed/api/load-feed.test.ts` | `npm test` | `apps/web` |
| AC6 | Backward empty state is honest | `feed-view.test.tsx`, one test: backward direction, empty page, tag set, `requests: 5`, `prevCursor` non-null -> text does not contain "first", a `‹ Previous page` link is present; same with `prevCursor` null -> no Previous link, `Next page →` present. Catches the false "first N pages" claim. Forward copy stays covered by existing T22 | unit (component) | vitest + Testing Library | none | `npx vitest run features/feed/components/feed-view.test.tsx` | `npm test` | `apps/web` |
| AC4 | Next then Previous returns the same cards against the stub | `feed.e2e.ts`, one test in "navigation": on `/` record the card titles; click `Next page →`; click `‹ Previous page`; URL `cursor` equals `fixtures.prev_cursor` byte-identical and `dir` is `prev`; titles equal the recorded list in order; no Previous link on that page | e2e | Playwright | stub: page2 returns `prev_cursor`, that cursor returns page1 with `prev_cursor: null`; `prev_cursor` added to `populated.json` | `npx playwright test e2e/feed.e2e.ts -g "Previous"` | `npm run test:e2e` | `apps/web` |
| AC7 | `dir` parsing and pass-through | No new test. Covered by: the AC4 e2e (a `dir=prev` URL renders the backward page), the AC5 unit test (direction reaches the drain), the existing `search-params.test.ts` cases migrated to the new field (an unrelated or absent `dir` stays forward), and the unchanged `error-*-with-cursor` baselines. A dedicated parser test for `dir` alone would restate a one-line condition | — | — | migrate `search-params.test.ts` expectations | `npx vitest run features/feed/lib/search-params.test.ts` | `npm test` | `apps/web` |
| AC8 | Nothing else changed | Existing suites: 16 baseline scenarios unchanged; `ok-last-page` DOM re-captured once (`--update-snapshots` on that scenario only), diff reviewed (only Previous links added), styles and console unchanged; `conventions.test.ts` (barrel, `import type`, no `.sort`/`.reverse`); `types.generated.test.ts` (drift); `load-feed-state.test.ts` (log line) | unit + e2e | vitest, Playwright | `npx playwright install chromium` once | `npx playwright test e2e/feed.e2e.ts -g "ok-last-page" --update-snapshots` then `npx playwright test e2e/feed.e2e.ts` | `npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e` | `apps/web` |
| AC9 | Docs say the web uses `prev_cursor` | Review: `git diff -- README.md docs/runbooks.md apps/web/AGENTS.md` | review | — | none | `grep -n "does not use .prev_cursor" README.md` returns nothing | — | repo root |
| AC10 | Real API round trip | Manual: `npm run dev` with the real `FEED_API_BASE_URL` in `.env.local`; `/` -> Next -> Previous shows the same 5 cards, first page has no Previous. Record in `tasks.md`, or record as pending for the human if the env is not available | manual (local) | browser | `.env.local` with `FEED_API_BASE_URL` | `npm run dev` | — | `apps/web` |

## Revision log
- Revision 1 (2026-11-10): first draft.

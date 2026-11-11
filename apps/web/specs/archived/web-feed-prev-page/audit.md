# Audit: Web Feed Previous Page

Scope of review: working tree on `feat/feed-prev-cursor` (base `c9c0c2f`, nothing committed). The earlier
uncommitted frontend work (PAGE_SIZE 5, top pager, relevance text hidden, chip note removed, re-captured
baselines, regenerated `types.generated.ts`) is out of scope except where it interacts with this spec. Files read in
full or by diff: `app/page.tsx`, `features/feed/api/{client,load-feed,load-feed-state}.ts`,
`features/feed/lib/{href,search-params}.ts`, `features/feed/components/{pagination,feed-view}.tsx`, their tests,
`e2e/feed.e2e.ts`, `e2e/stub/feed-api-stub.mjs`, `e2e/fixtures/populated.json`, all 17 DOM baselines and the style
baselines, root `src/api/handler.py` (cursor rules), root `specs/current/feed-api.md` (FA-3, FA-7, FA-R2) and
`specs/archived/feed-prev-cursor/execution-plan.md` (cursor rule table).

## AC results

| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | `pagination.tsx` renders `‹ Previous page` iff `prevCursor !== null`, between First and Next, href `feedHref({tag, cursor: prevCursor, direction: 'prev'})`; `FeedList` renders the bar above and below, `FeedNoMatch` once. `feed-view.test.tsx` "shows First, Previous, Next only where each applies" asserts order in both bars and href `/?cursor=a%2Bb%2Fc%3D&dir=prev` (rerun, `npm test` 400/400). `ok-last-page` baseline shows `/?cursor=e2e%2Bprev%2Fcursor%3D%3D&dir=prev` in both bars (rerun, e2e). |
| AC2 | PASS | First/Next rules unchanged in `pagination.tsx`; Next href has no `dir` (`feedHref` adds `dir` only when `direction==='prev'`, which Pagination passes only for Previous). Bar returns `null` when no link applies. Existing T25 and new test (b) assert Next href `/?cursor=n` (rerun). |
| AC3 | PASS | `client.ts` normalises `prev_cursor` exactly like `next_cursor`, never throws. `client.test.ts` "fetchFeed prev_cursor normalisation" `it.each` over string/undefined/null/""/42 (rerun). End to end: all stub responses other than the two Previous ones omit `prev_cursor` and their baselines pass (rerun). |
| AC4 | PASS | e2e "Previous page after Next page shows the same cards": URL `cursor` byte-equal to `fixtures.prev_cursor` (`e2e+prev/cursor==`), `dir=prev`, titles equal the first page in order, no Previous link (rerun, 54/54). The test does not assert that `Next page →` is present on that page (F7). |
| AC5 | PASS | `load-feed.ts`: `follow = backward ? prevCursor : nextCursor`, loop bounded by `requests < MAX_DRAIN_REQUESTS`, cursor passed verbatim, `dir` not passed to `fetchFeed`. Two tests in `load-feed.test.ts` "loadFeed backward drain" assert hop cursors `B0,B1,B2` (never `F*`) and the 5-call cap with `prevCursor` `B5` kept (rerun). Drain analysis below. |
| AC6 | PASS | Backward copy in `FeedNoMatch` ("We searched N pages back…" / "There are no earlier cards…"), forward copy byte-unchanged. Test "backward no-match state never claims 'the first N pages'…" (rerun). Related defect outside the AC6 inputs: F2. |
| AC7 | PASS (logic) / coverage gap | `parseFeedSearchParams`: `direction = cursor !== undefined && params.dir === 'prev' ? 'prev' : undefined` (an array `dir` is not `=== 'prev'`, `dir` without cursor is forward). `fetchFeed` builds the URL from `limit`, `tag`, `cursor` only, so `dir` never reaches feed-api. `FeedError` retry href passes `direction`. By inspection (rerun of reading); no test pins the parser rule, the threading, or the retry `dir` (F3). |
| AC8 | PASS | 17 baseline scenarios pass (rerun). Pager-bar markup compared HEAD vs working tree for every DOM baseline: only `ok-last-page` differs, gaining the Previous link in its bars (HEAD one bar `← First page`; now two bars `← First page`, `‹ Previous page`). Bar count doubles in list-state baselines from the earlier top-pager work, not this spec. Style diffs of `ok-last-page` have the same hunk shape as every other list-state baseline (earlier chip-note/relevance work); `console/` and `stderr/` unchanged. Barrel exports exactly `FeedView`, `loadFeedState`, `parseFeedSearchParams` (no diff). `feed_fetch_failed` keys and order unchanged. `feed.module.css`, `globals.css` unchanged; `types.generated.ts` diff is the earlier regeneration, and `types.generated.test.ts` (drift) passes. `npm test` 400/400, `npm run build` ok, `npm run test:e2e` 54/54 (rerun). `npm run lint`/`typecheck`: reused from executor (0 errors, 1 pre-existing warning; clean), not re-run per role; `next build` ran its TypeScript step clean (rerun). |
| AC9 | FAIL | Root `README.md:79` still says "The web app does not use `prev_cursor` yet (a follow-up `apps/web` spec)"; `docs/runbooks.md` web check has no Previous step; `apps/web/AGENTS.md` WEB-4 unchanged. O6 left for the documenter (rerun, grep). F1. |
| AC10 | N/A (pending human) | Not run: needs `FEED_API_BASE_URL` from `apps/web/.env.local`, which the auditor may not read. O8 open (unavailable). F6. |

### Drain analysis (AC5, FA-3, FA-7, FA-R2)

Against `src/api/handler.py` and the `feed-prev-cursor` rule table:

- **No skipped card.** Every hop follows a server-issued `prev_cursor` of a page with zero cards. An empty backward
  page's `prev_cursor` is "backward at `LastEvaluatedKey`" (strictly further back) or `null` at the start of feed,
  so the walk covers a contiguous stretch. The page shown offers its own `next_cursor` (FA-7: non-null on every
  backward page), which crosses the same empty stretch forward. No card is lost.
- **No loop.** Each hop's key is strictly further back, and the loop is capped at 5 requests in total either way.
- **Cap.** `requests` starts at 1 and the loop requires `requests < 5`, so at most 5 `fetchFeed` calls (unit test
  enforces a 6th call throws).
- **Forged `dir=prev`** on a forward cursor: the first request is still the forward page (direction lives in the
  cursor, server-side). Only if it is empty does the loader follow its `prev_cursor` (backward at its LEK, or from
  end of feed), which re-reads that empty stretch backward and continues to earlier pages: server-issued, contiguous,
  capped at 5. It can show an earlier page than the reader expected, never skip a card or exceed the cap. A
  non-empty forward page is shown unchanged. `dir=prev` without a cursor is forward by construction.
- No over-fetch or extra query compensating FA-R2.

## Binding-constraint compliance

| Constraint | Status | Evidence |
|---|---|---|
| Cursors opaque; direction only from `dir=prev` | PASS | No cursor decoding anywhere; `direction` comes only from `parseFeedSearchParams`. |
| Cursor sent is exactly the returned string; `dir` never forwarded | PASS | `loadFeed` passes `follow(page)` verbatim; `fetchFeed` sets only `limit`, `tag`, `cursor`. |
| Drain direction rule table, ≤ `MAX_DRAIN_REQUESTS` | PASS | `load-feed.ts` loop; unit tests (rerun). |
| `prev_cursor` normalisation mirrors `next_cursor`, never throws | PASS | `client.ts`; `client.test.ts` (rerun). |
| Link hrefs, texts, DOM order | PASS | `pagination.tsx`, `href.ts`; component test and `ok-last-page` baseline (rerun). |
| No edit to `feed.module.css`, `globals.css`, `types.generated.ts` | PASS | `git diff HEAD` empty for both CSS files; `types.generated.ts` change is the earlier generator output (drift test green). |
| Barrel unchanged; `components/`/`lib/` `import type` only; log line unchanged | PASS | `index.ts` no diff; `conventions.test.ts` green (rerun). |
| No FA-R2 compensation | PASS | No over-fetch, extra query or merge. |
| Keep earlier working-tree changes; re-capture only `ok-last-page` | PASS | Pager markup comparison above; other baseline diffs match the earlier intentional UI changes only. |
| WEB-1 (server-side, no `NEXT_PUBLIC_`) | PASS | grep under `features/feed` (non-test) finds no `NEXT_PUBLIC`. |
| WEB-3 (no `.sort(`/`.reverse(`) | PASS | grep finds none under `features/feed` (non-test). |
| WEB-5 (one render state) | PASS | Still one of four branches; see F2 for the copy in one branch. |
| Invariant 3 (thin `page.tsx`) | PASS | One extra destructured field passed through. |
| Dependencies | PASS | `package.json`/`package-lock.json` unchanged vs HEAD. |
| No Vercel command, no CSS or generated-types hand edit | PASS (as far as observable) | No Vercel config or file changes; CSS untouched; generated types match the generator (drift test). Shell history is not observable. |

## Test coverage

| AC | Test | Status |
|---|---|---|
| AC1, AC2 | `features/feed/components/feed-view.test.tsx` "FeedView previous page link › shows First, Previous, Next only where each applies" | PASS |
| AC3 | `features/feed/api/client.test.ts` "fetchFeed prev_cursor normalisation" (`it.each`, 5 cases) | PASS |
| AC4 | `e2e/feed.e2e.ts` "navigation › Previous page after Next page shows the same cards" | PASS |
| AC5 | `features/feed/api/load-feed.test.ts` "loadFeed backward drain (direction prev)" (2 tests) | PASS |
| AC6 | `features/feed/components/feed-view.test.tsx` "backward no-match state never claims 'the first N pages'…" | PASS |
| AC7 | None effective: `search-params.test.ts` not migrated, and its `toEqual` ignores an `undefined` `direction`; `load-feed-state.test.ts:45` `toHaveBeenCalledWith({tag, cursor})` ignores it too | MISSING (F3) |
| AC8 | Existing e2e baselines, `conventions.test.ts`, `types.generated.test.ts`, `load-feed-state.test.ts` | PASS |
| AC9 | Review | FAIL (F1) |
| AC10 | Manual | Not run (F6) |

Each new test would fail if its behaviour were removed (by inspection: following `nextCursor` backward fails the
hop-cursor assertion; dropping normalisation fails the `it.each`; dropping the link or `dir` fails the href
assertions; reverting the copy fails `not.toMatch(/first/i)`). No red run is recorded in `tasks.md` (F4).

The e2e race fix: in the new Previous flow, `await page.waitForURL((u) => u.searchParams.get('dir') === 'prev')`
precedes the synchronous `page.url()` reads. The Next.js `<Link>` navigates client-side, so `page.url()` may still
read page 2's URL right after `click()`. The wait adds no assertion and removes none; the following `cursor` and
`dir` assertions remain exact (`toBe(fixtures.prev_cursor)`, `toBe('prev')`), and the titles comparison is preceded
by an auto-retrying `toBeVisible` on card 1 (absent from page 2). Legitimate race fix, not a weakening. The
`.first()` additions in the existing navigation test come from the earlier top-pager work (two links per name),
not this spec; no assertion there changed.

Test minimality: new tests are exactly the § Validation set (the AC5 row's single test is split into two `it`
blocks; same scope). The "shows Next page both above and below" test and the removed T33 belong to the earlier
work, out of scope. No tautology, framework or source-grep test added.

### Tier Results

| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (component), vitest + Testing Library | 2 new in `feed-view.test.tsx` | AC1, AC2, AC6 | Yes (`okPage` gains `prevCursor`) | rerun, `npm test` 400/400 | PASS | — |
| unit, vitest | 1 `it.each` in `client.test.ts`, 2 in `load-feed.test.ts` | AC3, AC5 | Yes (page helpers gain `prevCursor`) | rerun | PASS | — |
| e2e, Playwright | 1 new in `feed.e2e.ts` | AC4 (and AC8 baselines) | Yes (stub serves `prev_cursor`, fixture gains `prev_cursor`; no new dev dependency or config) | rerun, `npm run test:e2e` 54/54 | PASS | F7 |
| — (AC7 row, migration only) | none effective | AC7 | Migration of `search-params.test.ts` not done | rerun | MISSING | F3 |
| review | — | AC9 | — | rerun (grep) | FAIL | F1 |
| manual (local) | — | AC10 | `.env.local` not readable by auditor | not run: secrets denied | N/A | F6 |

No test exists at a tier § Validation does not name.

## Findings

| Id | Severity | Finding | Closure condition | Status |
|---|---|---|---|---|
| F1 | CRITICAL (AC9) | Docs not updated: `README.md:79` still says "The web app does not use `prev_cursor` yet"; `docs/runbooks.md` web browser check has no Previous step; `apps/web/AGENTS.md` WEB-4 does not name the direction rule. O6 open. | The three edits are made; `grep -n "does not use .prev_cursor" README.md` returns nothing. | Open |
| F2 | HIGH (AC1/AC8, guarantee 7 honest copy, WEB-5) | `FeedView` now routes an empty page with `tag === undefined`, `nextCursor === null`, `prevCursor !== null` to `FeedNoMatch` with forward copy, which renders the heading **No cards tagged “undefined”** and body "No cards are tagged “undefined” right now." Reachable live: an unfiltered forward walk whose last page holds exactly PAGE_SIZE (5) cards gets a `LastEvaluatedKey` from real DynamoDB, so `Next page →` leads to an empty page with `next_cursor: null` and a non-null `prev_cursor` (handler: "backward from the end of the feed"), i.e. whenever the card count is a multiple of 5. Before this change that input rendered `FeedEmpty`. Verified by rendering `<FeedView cursor="LEK5" state={ok, cards [], nextCursor null, prevCursor "Bend"} />` from a scratch probe (rerun): text `No cards tagged “undefined”No cards are tagged “undefined” right now.← First page‹ Previous page`. | That input renders copy without the literal `undefined` (and keeps the Previous link), and a component test pins it. | Open |
| F3 | MEDIUM (AC7; plan § Consumers and migration, § Validation AC7 row) | `search-params.test.ts` was not migrated (no diff), although O5 records it as done. Even migrated, its `toEqual` ignores an `undefined` property. No test fails if the parser accepts `dir` without a cursor or a non-exact value, if `loadFeedState`/`page.tsx` drop `direction` (`load-feed-state.test.ts:45` `toHaveBeenCalledWith` ignores it; the AC4 e2e backward page is non-empty so direction has no effect there), or if `Try again` drops `dir`. The plan's AC7 coverage claim does not hold. | Either assertions that fail on those regressions (e.g. `toStrictEqual`/explicit `direction` checks, `loadFeed` called with `direction: 'prev'`), or a plan revision accepting the gap; O5's record corrected. | Open |
| F4 | MEDIUM (tasks.md evidence) | `tasks.md` O1–O4 Red/Green lines are unfilled template placeholders; no red evidence recorded. Status/Checkpoint sections are stale ("Specs drafted, not approved"). | Red and green commands and results recorded, or marked unavailable with a reason; status and checkpoint updated. | Open |
| F5 | MEDIUM (harny-feedback) | No `apps/web` Stop-hook record for this session's TS edits (the session ran from the repo root, whose hook is gated to `.py`), and `harny-feedback-apps-web.yml` has not run (nothing committed). Lint and typecheck results are reused from the executor only; `next build`'s TypeScript step passed (rerun). | A green `harny-feedback-apps-web.yml` run on the PR whose log shows `N of M command(s) ran` with N > 0. | Open |
| F6 | LOW (AC10) | Real-API dev-server check not run. | Human records `/` -> Next -> Previous shows the same 5 cards and no Previous on the first page, in O8. | Open (pending human) |
| F7 | LOW (AC4) | The AC4 e2e test does not assert that `Next page →` is present on the backward first page (part of AC4's example); covered at unit level by the AC6/AC1 tests only. | Assertion added, or accepted. | Open |

Notes (not findings):
- Layout default from the intent's open question is as predicted: on the last page `← First page` and
  `‹ Previous page` are pushed apart by `space-between`, Previous at the right edge. Accepted default; a design
  revision is the path to change it.
- The `ok-last-page` style baseline diff is the earlier work's (same hunk shape as the other list-state baselines);
  the Previous link adds no style change.

## Round 2 (2026-11-10)

Changes reviewed since round 1: `feed-view.tsx` (F2), `feed-view.test.tsx` (one test), `search-params.test.ts`
(one test), `load-feed-state.test.ts` (one test), root `README.md` line 79, `docs/runbooks.md` step 3,
`apps/web/AGENTS.md` WEB-4, `tasks.md`. No other tracked file changed relative to round 1 (`git status` delta:
`AGENTS.md`, `search-params.test.ts` added to the modified set; baseline diff stat identical to round 1, 22 files).

### Round-2 runs

| Check | Result | Label |
|---|---|---|
| `npm test` | 20 files, 403/403 passed | rerun |
| `npm run build` | compiled, TypeScript step clean | rerun |
| `npm run test:e2e` | 54/54 passed; no baseline file changed vs round 1 | rerun |
| `npm run lint` / `npm run typecheck` | 0 errors (1 pre-existing warning in `types.generated.ts`) / clean | reused (conductor), not re-run per role; CI not run |
| `grep -n "does not use .prev_cursor" README.md` | no match | rerun |

### F2 fix: every empty-page combination in `FeedView`

`state.status === 'ok'`, `cards.length === 0`. `drained` = the cursor in the request's direction is non-null.
`direction` can only be `'prev'` with a cursor (parser rule). "Before spec" = HEAD behaviour for the same inputs
(HEAD had no `prevCursor`, so it is treated as absent there).

| # | dir | tag | next | prev | Branch | Heading / body | vs before spec |
|---|---|---|---|---|---|---|---|
| 1 | fwd | set | N | any | no-match, drained | "No matches found yet" / "We searched the first N … for “t” …" | Unchanged copy; Previous link added when `prev` set |
| 2 | fwd | set | null | any | no-match | "No cards tagged “t”" / "No cards are tagged “t” right now." | Unchanged copy (AC6); Previous link added when `prev` set |
| 3 | fwd | none | N | any | no-match, drained | "No matches found yet" / "We searched the first N pages of the feed …" | Unchanged |
| 4 | fwd | none | null | P | no-match | **"No cards on this page" / "There are no cards on this page. Use the page links below."** + bar (First if cursor, Previous) | Was `FeedEmpty` at HEAD, "tagged “undefined”" in round 1; now neutral and honest |
| 5 | fwd | none | null | null | empty | "No cards yet" | Unchanged |
| 6 | prev | any | any | P | no-match, drained | "No earlier matches found yet" / "We searched N pages back[ for “t”] …" | New (AC6) |
| 7 | prev | any | N | null | no-match | "No earlier matches" / "There are no earlier cards[ tagged “t”]. Use the next page link below." | New (AC6) |
| 8 | prev | none | null | null | empty | "No cards yet" | Unchanged branch |
| 9 | prev | set | null | null | no-match | "No earlier matches" / "… Use the next page link below." with no Next link | New; unreachable against FA-7 (a backward page always has a non-null `next_cursor`); only a hand-made `dir=prev` URL against an older backend can produce it. Note, not a finding |

No branch can render the literal `undefined` any more: every `tag` interpolation is guarded by `tag ?` or sits in
case 1/2 where `tag` is set. The branch selector in `FeedView` is unchanged from round 1, so cases 1–3 and 5 keep
their state and copy; the only behavioural change from round 1 is case 4's copy. The regression test
"without a tag it never says 'tagged undefined' and keeps the Previous link" (`feed-view.test.tsx:272`) fails on
round-1 code (`/undefined|tagged/`) and on HEAD-like routing to `FeedEmpty` (no Previous link). No e2e baseline
covers case 4, so none changed, as expected. **F2 closed.**

Notes (pre-existing, not findings): case 2 with a live `prev` says "No cards are tagged “t” right now" although
earlier pages may hold matches; that is the unchanged forward copy AC6 requires. The `FeedView` doc comment still
describes `feed-no-match` as "a tag is active", which was already imprecise before this spec (case 3).

### Other findings, round 2

- **F1 closed.** `README.md:79` now says the web feed uses `prev_cursor` for `‹ Previous page`
  (`web-feed-prev-page`), with the `dir=prev` hint never sent to feed-api; `docs/runbooks.md` step 3 adds Next then
  Previous returns the same cards, `dir=prev` in the URL, no Previous on the first page; `apps/web/AGENTS.md` WEB-4
  names the direction rule. AC9 PASS.
- **F3 closed.** `search-params.test.ts` "direction is 'prev' only for dir=prev together with a cursor" asserts
  `direction` explicitly (`toBe`/`toBeUndefined`) for `cursor+dir=prev`, `dir=prev` without cursor, `dir=other`,
  and a repeated `dir`. `load-feed-state.test.ts` "passes direction 'prev' through to loadFeed" asserts
  `toHaveBeenCalledWith({…, direction: "prev"})`, which fails if `loadFeedState` drops the field (an expected
  defined property missing from the actual call fails the match). Residual, accepted as low value: the one-line
  pass-through in `app/page.tsx` and the `Try again` `dir` are still covered by inspection only.
- **F4 closed, residual F8.** Red results are now recorded per outcome (as prose, without the exact command line or
  output; accepted as `reused`), and Status and Checkpoint are current. Still stale: "Working state" (says O1–O5, O7
  done, next step documenter O6), O7 evidence says vitest 400/400 (now 403), and O5's wording ("expectations gain the
  direction field") describes the plan, not the added test. Raised as F8 (LOW).
- **F5 open, downgraded to LOW.** The conductor re-ran lint and typecheck, and `next build`'s TypeScript step is
  clean (rerun), but there is still no `apps/web` Stop-hook record or `harny-feedback-apps-web.yml` run. Closes with
  the PR's green CI run.
- **F6 open (pending human).** AC10 needs `.env.local`, which agents may not read.
- **F7 open (accepted by the executor as nice-to-have).** No change.

### Round-2 AC status

AC1–AC9 PASS; AC10 N/A (pending human, F6). AC7 coverage now PASS (F3 closed). § Validation tier table unchanged
from round 1 except: the AC7 row is now covered by unit tests (`search-params.test.ts`, `load-feed-state.test.ts`;
these sit at the unit tier named elsewhere in § Validation, using the AC7 row's own migration setup) and the review
row (AC9) is PASS.

### Findings (round 2 state)

| Id | Severity | Closure condition | Status |
|---|---|---|---|
| F1 | CRITICAL | Docs edited; grep empty | Closed (round 2, verified) |
| F2 | HIGH | No `undefined` copy; component test | Closed (round 2, verified) |
| F3 | MEDIUM | Effective AC7 tests | Closed (round 2, verified; page/retry residual accepted) |
| F4 | MEDIUM | Red/green recorded; status/checkpoint updated | Closed (round 2), residual in F8 |
| F5 | LOW (was MEDIUM) | Green `harny-feedback-apps-web.yml` on the PR with N > 0 commands run | Open |
| F6 | LOW | Human records AC10 in O8 | Open (pending human) |
| F7 | LOW | e2e asserts `Next page →` on the backward first page, or accepted | Open (executor declined; nice-to-have) |
| F8 | LOW | `tasks.md` Working state, O7 test count and O5 wording updated | Open |

## Audit log

| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-11-10 | REJECTED | AC9 unmet (F1, documenter's O6 not done); reachable "undefined" copy introduced by the FeedView branch change (F2). Code for AC1–AC8 otherwise compliant; drain logic verified against FA-3/FA-7. Unit 400/400, build ok, e2e 54/54 rerun. |
| 2 | 2026-11-10 | APPROVED WITH RESERVATIONS | F1–F4 closed after verification; F2 checked over every empty-page input combination. Unit 403/403, build ok, e2e 54/54 rerun, baselines unchanged. Open: F5 (CI not run), F6 (AC10 human), F7, F8 (all LOW). |

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: Round 2 closes every blocking finding. AC1–AC9 pass, the F2 fix is honest for every empty-page input
without changing any other state, and the suite reruns green with no baseline change. AC10 and the CI run are
still human or pipeline steps.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F5: lint and typecheck have no hook or CI record yet; confirm the PR's `harny-feedback-apps-web.yml` run is green.
- F6: AC10 real-API check pending the human (record in O8).

**Recommendations** (nice to have):
- F8: refresh `tasks.md` Working state, the O7 count (403) and O5 wording.
- F7: assert `Next page →` on the backward first page in the e2e flow.

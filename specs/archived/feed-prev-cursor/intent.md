# Intent: feed-prev-cursor

Shipped: 2026-11-10

Revision: 2
Approval: Approved revision 2 on 2026-11-10 under the human's standing instruction to run fully autonomously and auto-accept every gate (recorded by the conductor, not by the architect). Q1 = option A, Q2 = accept, both chosen by the conductor under that instruction.

## Outcome
`GET /v1/cards` gains backward paging. Every 200 response carries a new `prev_cursor` next to
`next_cursor`. A client sends it back as the same `?cursor=` parameter to get the page before the one it
is on. The server stays stateless: the opaque cursor holds a position and a direction, and a backward
request is one reversed `Query` on the same `feed-by-score` index. The public request shape, the IAM grant,
the forward behavior and every cursor issued before this change are unchanged. The frontend does not use
the new field yet. A separate `apps/web` spec follows once this is deployed and live-verified.

## Acceptance criteria

Notation: `c1..c7` are seven cards in feed order (relevance desc, then published desc). `limit` is the
same on every call of an example. "Following" a cursor means `GET /v1/cards?limit=<same>&cursor=<token>`
(plus the same `tag`, if any).

- **AC1** Every 200 body has a `prev_cursor` key, a string or `null`. On forward pages it is `null` only on
  the first page of the feed: a request without a `cursor`, or one whose cursor points at the start of the
  feed (see AC4). Every other forward page has a non-null `prev_cursor`.
  Example: `GET /v1/cards?limit=3` -> `{"cards":[c1,c2,c3],"next_cursor":"<N1>","prev_cursor":null}`;
  `GET /v1/cards?limit=3&cursor=<N1>` -> `{"cards":[c4,c5,c6],"next_cursor":"<N2>","prev_cursor":"<P2>"}`.

- **AC2** Without a tag filter, and with an unchanged dataset, following `prev_cursor` from forward page
  k+1 returns exactly the cards of forward page k, in the same order, for every k >= 1. The page reached
  that way has `prev_cursor: null` exactly when it is page 1. This holds when cards share the same
  relevance and published date (equal `gsi_sk`) across a page boundary.
  Example: following `<P2>` -> `{"cards":[c1,c2,c3],"prev_cursor":null,"next_cursor":"<N1'>"}`.
  Following `<N2>` -> `{"cards":[c7],"next_cursor":null,"prev_cursor":"<P3>"}`, and following `<P3>` ->
  `{"cards":[c4,c5,c6],"prev_cursor":"<P2'>"}` with `<P2'>` non-null.

- **AC3** A page reached backward always has a non-null `next_cursor`. Following it returns forward to the
  cards after that page with no gap and no repeat. Without a tag filter it returns exactly the page the
  client came from (round trip next -> prev -> next).
  Example: following `<N1'>` from the AC2 example -> `{"cards":[c4,c5,c6],...}`.

- **AC4** With or without a tag filter, no backward or forward move skips or repeats a card. From any page,
  following `prev_cursor` until it is `null` yields exactly the matching cards before that page, in feed
  order. From the page where `prev_cursor` is `null`, following `next_cursor` until it is `null` yields
  exactly the matching feed. A backward page may be short or empty while its `prev_cursor` is non-null,
  the same rule FA-3 gives `next_cursor`. **Accepted reservation (human-approved):** with a tag filter
  active, backward page boundaries may differ from the forward pages, because DynamoDB applies the filter
  after `Limit`. No over-fetch is added to align them.
  Example (`tag=python`, only c4 and c6 match, `limit=3`): forward pages are `[]`, `[c4,c6]`, `[]`
  (`next_cursor: null` on the third). Following prev from the third page gives `[c4,c6]`, then `[]` with
  `prev_cursor: null`. The cards seen are the same, the boundaries are not.

- **AC5** (compatibility) A cursor issued before this change keeps working: the server reads it as a
  forward cursor and returns the same page it returned before. A forward `next_cursor` issued after the
  change is byte-for-byte the token the current code would issue for the same position.
  Example: `?cursor=eyJjYXJkX2lkIjoiMGExYjJjM2Q0ZTVmNjA3MSIsImdzaV9wayI6IkNBUkQiLCJnc2lfc2siOiIwMDgjMjAyNi0wOC0yOSJ9`
  (the encoding of `{"card_id":"0a1b2c3d4e5f6071","gsi_pk":"CARD","gsi_sk":"008#2026-08-29"}`) -> 200, the
  page after that key, as today.

- **AC6** (failure) Any cursor that is not exactly one of the shapes the server issues returns the existing
  400 and makes no DynamoDB call. This covers bad base64 or JSON, a wrong key set, a non-string value, a
  foreign `gsi_pk`, an unknown direction value and a direction marker with a partial key.
  Example: `?cursor=<base64url of {"card_id":"x","dir":"sideways","gsi_pk":"CARD","gsi_sk":"005#2026-08-01"}>`
  -> `400 {"error":"invalid_cursor","message":"cursor is malformed or has been tampered with"}`.

- **AC7** (compatibility) Each request, forward or backward, makes exactly one `Query`, on the
  `feed-by-score` index, and never a `Scan`. The Lambda role is unchanged: one `dynamodb:Query` grant on
  the index ARN (AD-6), with no new action or resource. The synthesized `AiRadarFeedApi` IAM policy is
  identical before and after.

- **AC8** (compatibility) The response contract stays `v1`: `FeedResponse` gains an optional, nullable
  `prev_cursor` and nothing else changes. `CARD_SCHEMA_VERSION`, the route `/v1/cards` and the artifact
  name `docs/api/feed-api.v1.schema.json` stay as they are. The committed schema artifact and
  `apps/web/features/feed/api/types.generated.ts` are regenerated from the model, not hand-edited, and no
  frontend behavior changes. The existing forward guarantees (FA-1 to FA-6, invariants 1 and 2) still hold,
  and the existing feed tests pass.

- **AC9** (live, human-run after merge) After the PR is merged and the CI deploy of `AiRadarFeedApi`
  succeeds, the real API shows:
  - the first page has `prev_cursor: null`;
  - page 2's `prev_cursor` is non-null and returns exactly page 1's cards in the same order;
  - next -> prev -> next returns page 2 again;
  - a tag-filtered backward call returns 200;
  - no request returns 500 or `AccessDeniedException` (the AD-6 grant is enough).
  Example: `curl "$FEED_API_URL/v1/cards?limit=2"` -> `"prev_cursor": null`.

## Scope
**In**
- `prev_cursor` in `FeedResponse` and in every 200 response of `GET /v1/cards`.
- Direction-aware opaque cursors in `src/api/cursor.py`, accepted through the existing `?cursor=`.
- The backward query and the cursor rules for each page in `src/api/feed.py` and `src/api/handler.py`.
- Regenerating `docs/api/feed-api.v1.schema.json` and `apps/web/features/feed/api/types.generated.ts`.
- The minimum tests listed in `execution-plan.md` § Validation.
- The README and runbook notes on the new field, and the post-merge live check.

**Out**
- Any `apps/web` behavior change (a "Previous" control, using `prev_cursor`, backward draining of empty
  filtered pages). A follow-up spec in `apps/web/specs/` covers it.
- Making filtered backward page boundaries match the forward ones (over-fetch, extra queries).
- A new query parameter, a page number, an offset or a server-side page store.
- Any IAM, CORS, throttling or other infrastructure change.
- A schema version bump.

## Constraints
- Stateless: everything the server needs is in the cursor. No session, no table, no cache.
- Exactly one DynamoDB `Query` per request, on `feed-by-score`, with no change to the AD-6 index-only grant
  (`feed-api` FA-1, FA-4).
- The cursor stays opaque and stays the validation boundary: a decoded cursor reaches DynamoDB only after
  it passes the exact-shape check (archived `feed-api` contract, Guarantee 7).
- Plane B code only (`src/api/`, `src/contracts/`). Planes never import each other
  (`docs/architecture-principles.md` boundary 1).
- `uv` only. The Lambda image's `api` dependency group gains nothing.
- Lean style: small functions, no new abstraction layer.
- Delivery goes through the live CI/CD pipeline: merging to `main` deploys `AiRadarFeedApi` (the
  `src/api/` and `src/contracts/` paths map to it in `scripts/ci/deploy_plan.py`), and the smoke check runs.
  The human merges and runs the live check.
- The spec must not disturb the uncommitted `apps/web` work in the tree (feed components, e2e baselines).
  Only `types.generated.ts` changes under `apps/web/`.

**Current-truth notes (`harny-sync` lookup, 2026-11-10)**
- `feed-api` FA-1 says the feed is returned "in descending `gsi_sk` order". Backward requests query in
  ascending order, but the page they return is still in descending order, so the observable ordering is
  unchanged. FA-1 gets a wording amendment at archive time.
- `feed-api` FA-3 and archived Guarantee 5 say `next_cursor` is null if and only if DynamoDB returned no
  `LastEvaluatedKey`. That stays true for forward pages. On a backward page, `next_cursor` is never null
  (AC3), so FA-3 is amended at archive time, not contradicted silently.
- `specs/current/ci-cd.md` (synced 2026-10-28) says the pipeline is NOT live. `README.md` § Live state
  (the source of truth under `CLAUDE.md`) says it is live, with two successful `backend deploy` runs on
  2026-10-28. This spec follows `README.md`. `ci-cd.md` is stale, and the next `harny-sync` archive should
  fix it.
- The `export_api_schema.py` and `src/contracts/card.py` docstrings call any `CardOut`/`FeedResponse`
  change "a BREAKING API change". This spec treats an additive optional response field as non-breaking
  (AC8). See the plan's decision and ADR candidate.

## Open questions
- None open. Q1 and Q2 were answered by the conductor on 2026-11-10, relayed as the human's decision:
  Q1 = option A (the backward query reads `limit + 1`), Q2 = accept old forward cursors unchanged. The
  human still records approval of this file below. The original questions are kept for the record.
- **Q1 (resolved: option A).** The brief says the backward query uses the same `Limit` and
  also that `prev_cursor` is `null` once the backward query reaches the start of the index. Real DynamoDB
  cannot do both. When a query stops at exactly `Limit` items, DynamoDB returns a `LastEvaluatedKey` even if
  nothing follows (Developer Guide, "Paginating table query results"). Going back from page 2 always reads
  exactly `limit` items, so with the same `Limit` the page-1 result would carry a non-null `prev_cursor`
  that leads to an empty page. `moto` hides this: it returns a `LastEvaluatedKey` only when another item
  exists, so the offline tests would pass and the live check would fail.
  **Recommended:** the backward query uses `Limit = limit + 1`, returns at most `limit` cards and uses
  the extra item only to decide whether anything lies before. That is one extra index item read per
  backward call, still one `Query`. It is not the filter over-fetch the brief rules out. AC2 is written for
  this option.
  **Alternative:** keep the same `Limit` and change AC2. On page 1 reached backward, `prev_cursor` may be
  non-null, and following it returns `{"cards":[],"prev_cursor":null}` with a `next_cursor` back to page 1.
  The live check in AC9 passes either way, but the future "Previous" button would show on page 1.
- **Q2 (resolved: accept).** Old cursors are accepted, not rejected (AC5). The forward encoding is kept
  byte-identical, so an old cursor is already a valid forward cursor and needs no extra code. Rejecting old
  cursors with 400 would break the `apps/web` URLs that already carry `?cursor=` (`app/page.tsx`
  passes it from the address bar), including bookmarked or shared ones. Please confirm.

## Revision history
- Revision 1 (2026-11-10): first draft.
- Revision 2 (2026-11-10): Q1 resolved as option A and Q2 as accept (conductor-relayed decisions).

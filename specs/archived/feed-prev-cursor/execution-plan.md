# Execution Plan: feed-prev-cursor

## Guidance consulted
- `CLAUDE.md` (uv only, lean style, planes never import each other, Context7 before relying on memory,
  the `--only-group` Docker gotcha) and `docs/architecture-principles.md` (boundaries 1 and 2: `Card` is
  the versioned contract, and no speculative layers).
- `harny-sync` lookup: `specs/current/_index.md`, `specs/current/feed-api.md` (FA-1 to FA-6, invariants 1
  and 2, FA-R1) and `specs/current/ci-cd.md` (CICD-5 path mapping, CICD-8 smoke). The feed API predates
  `harny-adr`, so no ADR covers the cursor or AD-6. Their rationale is in
  `specs/archived/feed-api/contract.md` (AD-6, Behavior Guarantees 1 to 9), which was read for it.
- Code: `src/api/{cursor,feed,handler,config,dynamo}.py`, `src/contracts/card.py`, `export_api_schema.py`,
  `infra/lib/feed_api.py` (the `FeedGsiQuery` statement), `scripts/ci/deploy_plan.py`, `scripts/ci/smoke.py`,
  `src/curation/dynamo.py` (`gsi_sk = f"{relevance:03d}#{published}"`, which is not unique).
- Tests: `tests/test_feed_cursor.py`, `tests/test_feed_query.py`, `tests/test_feed_api_handler.py`,
  `tests/test_feed_api_contract.py`, `tests/test_contracts_card.py`, `tests/conftest.py` (`seed_cards`,
  `put_card_item`, the moto table with the `feed-by-score` GSI).
- Consumers: `apps/web/scripts/generate-api-types.mjs`, `apps/web/features/feed/api/types.generated.ts` and
  its drift test `types.generated.test.ts`, `apps/web/features/feed/api/client.ts` (reads named fields only)
  and `apps/web/app/page.tsx` (passes `?cursor=` from the address bar).
- DynamoDB docs (Context7, Developer Guide "Paginating table query results"): a non-empty
  `LastEvaluatedKey` means the query stopped at `Limit` or 1 MB, not that more items exist. Only an absent
  key proves the end.
- moto 5.2.2 source (`moto/dynamodb/models/table.py`): it returns `LastEvaluatedKey` only when another item
  follows (unlike real DynamoDB), and it orders GSI ties by `(gsi_sk, card_id)`.
- `.claude/skills/high-value-tests/SKILL.md` for the test scope.

## Ownership
- `src/api/cursor.py`: direction-aware encode and decode, the trust boundary.
- `src/api/feed.py`: the backward query and the cursor positions of a page.
- `src/api/handler.py`: `prev_cursor` in the response, and direction in the log record (suggested).
- `src/contracts/card.py`: `FeedResponse.prev_cursor`. `docs/api/feed-api.v1.schema.json` is regenerated
  by `uv run export_api_schema.py`, and the `export_api_schema.py` docstring wording is corrected.
- `apps/web/features/feed/api/types.generated.ts`: regenerated only, with `npm run generate:types`.
- Tests: `tests/test_feed_cursor.py`, `tests/test_feed_api_handler.py`.
- Affected `specs/current` capabilities: `feed-api` (FA-1 wording, FA-3 amended for backward pages, a new
  requirement for backward paging and cursor compatibility, the accepted filtered-boundary reservation).
  `ci-cd`: no requirement change. Its "NOT live" status is stale (see `intent.md`, current-truth notes).

## Binding constraints
- One `Query` per request on `IndexName="feed-by-score"` with `Key("gsi_pk").eq("CARD")`. No `Scan`, no
  second call, no draining loop (source: `feed-api` FA-1, FA-2; archived contract "Exactly one query per
  call").
- No change to `infra/`. `dynamodb:Query` on the index ARN already covers `ScanIndexForward=True`: the
  direction is a request parameter of the same action, IAM has no condition key for it, and the
  `ExclusiveStartKey` stays in the same partition of the same index (source: `feed-api` FA-4, archived AD-6,
  `infra/lib/feed_api.py` `FeedGsiQuery`).
- Request surface unchanged: `tag`, `limit`, `cursor` only. Direction lives inside the opaque cursor
  (source: the human-approved brief).
- Forward cursor encoding is frozen: for a forward position with a key, `encode` must produce exactly
  today's token, base64url of compact key-sorted JSON of `{card_id, gsi_pk, gsi_sk}` with `=` stripped. This
  is what makes AC5 hold with no legacy branch (source: AC5; `tests/test_feed_cursor.py`
  `test_encode_cursor_is_valid_urlsafe_base64_of_key_sorted_json`).
- Decode accepts exactly the shapes the server issues, and anything else raises `InvalidCursorError` and
  becomes the existing 400 `invalid_cursor` before any DynamoDB call. `gsi_pk` must be `"CARD"` in every
  keyed shape (source: AC6; archived Guarantee 7).
- The page cursor rules below are binding, because AC1 to AC4 depend on them. How they are coded is not.

  | Request | Query | `next_cursor` | `prev_cursor` |
  |---|---|---|---|
  | Forward: no cursor, a start-of-feed cursor, or a forward key (old tokens included) | `ScanIndexForward=False`, `Limit=limit`, `ExclusiveStartKey`=key if any | forward at `LastEvaluatedKey`, else `null` (unchanged) | `null` if there was no key; else backward at the first card shown; else, on an empty page, backward at `LastEvaluatedKey`; else backward from the end of the feed |
  | Backward: a backward key, or from the end of the feed | `ScanIndexForward=True`, `Limit=limit+1` (Q1), `ExclusiveStartKey`=key if any; items reversed into feed order; if more than `limit` cards match, the one furthest from the anchor (first in feed order) is dropped | forward at the last card shown; else, on an empty page, forward at `LastEvaluatedKey`; else forward from the start of the feed | backward at the first card shown if a card was dropped; else backward at `LastEvaluatedKey`; else `null` |

  "At a card" means the key `{card_id, gsi_pk, gsi_sk}` of that card's index item. The keyless "start of
  feed" and "end of feed" cursors exist only for the empty-page cases a tag filter creates. Without them,
  an empty filtered page would anchor on an exclusive key and could skip a card that was shown on the
  neighbouring page (AC4).
- The `CardOut` projection must not change what the client sees. `CardOut` still drops `gsi_pk` and
  `gsi_sk` (`extra="ignore"`), and `embedding` stays unprojected (source: archived Guarantee 9; existing
  `test_returned_card_never_carries_index_keys_or_embedding`).
- `apps/web`: only `types.generated.ts` changes, and only through the generator. The tree has uncommitted
  `apps/web` feed work that belongs to the human. Do not stage, revert or reformat it (source: intent
  Scope Out; `git status` at baseline).

## Proposed approach
Revisable by the executor if it records why.
- Decision: direction lives in the opaque cursor, not in a `?direction=` parameter. Rationale: clients keep
  passing tokens through byte for byte (`apps/web` already does), and a mismatched cursor and direction
  pair cannot exist. Rejected: a separate parameter (two values that must agree, and a new 400 case);
  offsets or page numbers (DynamoDB has no offset, and they would need a scan or a counter); a server-side
  page stack (state, and it breaks statelessness).
- Decision: suggested token shapes. Forward with a key is the unchanged three-key object. Backward with a
  key is the same three keys plus `"dir": "prev"`. The keyless cursors are `{"dir": "next"}` (start of
  feed) and `{"dir": "prev"}` (end of feed). Decode returns a direction and an optional key. Rationale: the
  forward token stays byte-identical, and every shape is exact-match validated. Rejected: a versioned
  envelope for every cursor, such as `{"v":2,...}`. It would either reject old cursors (breaking `/?cursor=`
  URLs) or need a legacy branch, for no gain.
- Decision: old cursors are accepted as forward cursors, not rejected (AC5, intent Q2). It costs no code,
  because the forward encoding is unchanged.
- Decision: the backward query reads `limit + 1` items (intent Q1, resolved as option A). Rationale: real DynamoDB returns
  `LastEvaluatedKey` whenever it stops at exactly `Limit`, so with the same `Limit` page 1 reached backward
  would carry a dangling `prev_cursor`. The extra item tells "more before" from "start of feed" with
  certainty when unfiltered, so the result does not depend on that difference. Cost: one index item per
  backward call, still one `Query`. Rejected: the same `Limit` (a dangling cursor on page 1, hidden by moto);
  a second query to probe (breaks FA-1).
- Decision: project `gsi_sk` (and `gsi_pk`, or use the `FEED_GSI_PARTITION` constant) so the first and last
  card's index key can be built from the page. Rationale: the card's key is needed for its cursor, and
  deriving `gsi_sk` from `relevance` and `published` would copy Plane A's formula. Rejected: re-deriving the
  key (duplicated logic that drifts silently if PS-3 changes).
- Decision: `prev_cursor: str | None = None` on `FeedResponse`, with the same shape as `next_cursor`. The
  schema stays `v1`. Rationale: an added optional response field does not break a `v1` client. The model
  ignores unknown fields, `apps/web` reads named fields only, and the generated type gains an optional
  property. A bump would rename the route and the artifact for no client gain. Update the
  `FeedResponse` docstring (it flows into the generated TS comment) and the `export_api_schema.py`
  docstring: a removal, rename or type change bumps the version, and an added optional field does not.
- Suggestion: add `"direction"` and `"has_prev"` to the `feed_api_request` log record, so backward use is
  visible in CloudWatch. The existing log test only checks that the record exists.
- ADR candidates for `harny-adr` (numbers: next free after 0050; 0049 and 0050 are claimed by
  `apps/web/specs/web-chat-visitor-rate-limit`. Check `specs/current/_index.md` at ADR time):
  1. Backward paging is a stateless reversed `Query`, with the direction carried in the opaque cursor.
     Records the accepted reservation that filtered backward boundaries may differ from forward ones.
  2. The forward cursor encoding is frozen, so cursors issued before backward paging stay valid.
  3. The backward query reads `limit + 1` items to detect the start of the feed (only if Q1 option A is
     approved; otherwise record the dangling-cursor trade-off instead).
  4. An added optional response field does not bump `CARD_SCHEMA_VERSION`.

## Consumers and migration
- `apps/web`: `types.generated.ts` gains `PrevCursor` and `prev_cursor?: PrevCursor` through
  `npm run generate:types`. The drift test `features/feed/api/types.generated.test.ts` fails until the file
  is regenerated, so the regenerated file goes in the same PR. `client.ts` ignores the new field, and no
  behavior changes. The follow-up `apps/web` spec owns the UI. Note for it: an empty filtered backward page
  with a live `prev_cursor` needs the same bounded drain the forward path has.
- `scripts/ci/smoke.py`: `GET /v1/cards?limit=1` expects 200 and a `cards` list. That is unaffected.
- Existing tests: no assertion changes are expected. If `encode_cursor` or `decode_cursor` change
  signature (for example, decode returns a direction and a key), update the call sites in
  `tests/test_feed_cursor.py`, `tests/test_feed_query.py` (`_walk_all_pages_via_cursor`) and
  `tests/test_feed_api_handler.py`, and keep each test's assertion. In particular the exact-encoding test
  stays, because it guards AC5. If `query_feed`'s keyword arguments change, keep the forward call shape
  working, or migrate the `tests/test_feed_query.py` call sites without weakening them.
- Docs: the `FeedResponse` and `export_api_schema.py` docstrings in this PR. `docs/history.md` and the
  `feed-api` capability doc get updated in the documentation step, after the live check.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Real DynamoDB orders `gsi_sk` ties differently from moto, so a backward page is not the exact reverse | Low (the `ExclusiveStartKey` holds the table key, so the index has a total order in both directions) | Med (AC2 fails live) | The cursor always carries `card_id`. Live step L6 walks the whole feed at `limit=1` both ways. |
| moto returns no `LastEvaluatedKey` at an exact `Limit` boundary, so offline tests miss the dangling-cursor case | High (known) | Med | Option A (`limit+1`) makes the unfiltered start-of-feed decision independent of that. Live steps L2 and L3 check page 1 reached backward. |
| A filtered empty page anchors on an exclusive key and skips a card | Med without the keyless cursors | Med (AC4) | The binding cursor table, and the T4 dataset with leading and trailing non-matching runs. |
| Regenerating `types.generated.ts` picks up, or a commit sweeps in, the human's uncommitted `apps/web` work | Med | Med | Stage only `types.generated.ts` under `apps/web/`, and check `git diff --cached --stat`. |
| A forward token changes by accident (key order, separators, padding), so old `/?cursor=` URLs break | Low | High | The existing exact-encoding test, kept unchanged in its assertion. |
| The 1 MB response cap truncates a backward page | Very low (at most 101 small items, `embedding` not projected) | Low | The table rules use `LastEvaluatedKey` when present, so a truncated page still chains correctly. |
| The CI deploy fails or the smoke flakes | Low | Low | Re-run the smoke, or revert by PR (README, "CI/CD"). |

## Validation
Minimum high-value set (`high-value-tests`). Four new tests: two unit, two moto-backed through the
handler (the public contract, independent of how the logic is split between `feed.py` and `handler.py`).
Every other row relies on existing tests that must stay green.

New tests:
- **T1** (`tests/test_feed_cursor.py`, parametrized): encode then decode returns the same direction and
  key for each issued shape (forward with key, backward with key, start of feed, end of feed). Guards the
  direction marker and the exact inverse.
- **T2** (`tests/test_feed_cursor.py`, parametrized): decode rejects the new near-miss shapes with
  `InvalidCursorError`: an unknown `dir` value, a non-string `dir`, `dir` with a partial key, a keyless
  cursor with an extra key, a backward key with a foreign `gsi_pk`.
- **T3** (`tests/test_feed_api_handler.py`, unfiltered): seed 10 cards, some sharing `gsi_sk` across a page
  boundary (use `put_card_item`), and walk forward at `limit=3`. Assert the first page's `prev_cursor` is
  null and later pages' are non-null. Following page k+1's `prev_cursor` returns exactly page k's
  `card_id`s in order, with `prev_cursor` null iff k = 1. That page's `next_cursor` returns exactly page
  k+1. Each handler call makes one `query` (counting wrapper, as `_CountingQueryTable`).
- **T4** (`tests/test_feed_api_handler.py`, parametrized: no tag, and a tag): use a dataset whose matching
  cards are preceded and followed by non-matching runs at least one page long, so empty forward and backward
  pages and both keyless cursors occur. From every page of the forward walk, following `prev_cursor` until
  null yields exactly the cards before that page. From the page where it is null, following `next_cursor`
  until null yields exactly the full forward walk. No duplicates.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | `prev_cursor` null on the first page and non-null on later forward pages; null after a start-of-feed cursor | T3; T4 (the start-of-feed path) | integration | pytest + moto | existing `dynamo_table`, `put_card_item`, `seed_cards` fixtures and the `_use_table` monkeypatch | `uv run pytest tests/test_feed_api_handler.py -q` | `uv run pytest tests/ -q` | repo root |
| AC2 | Unfiltered backward page equals the forward page, ties across a boundary included; null `prev_cursor` exactly on page 1 | T3 | integration | pytest + moto | seed with shared `gsi_sk` values | `uv run pytest tests/test_feed_api_handler.py -q` | `uv run pytest tests/ -q` | repo root |
| AC3 | Backward page has a `next_cursor` that returns the page it came from (unfiltered) and has no gap or repeat (filtered) | T3; T4 | integration | pytest + moto | as AC1 | `uv run pytest tests/test_feed_api_handler.py -q` | `uv run pytest tests/ -q` | repo root |
| AC4 | Backward walk from any page equals the exact prefix, filtered and unfiltered; empty pages chain | T4 | integration | pytest + moto | leading and trailing non-matching runs of at least `limit` cards | `uv run pytest tests/test_feed_api_handler.py -q` | `uv run pytest tests/ -q` | repo root |
| AC5 | Forward tokens are byte-identical to today's, so an old token decodes as forward and returns the same page | T1 (forward case); existing `test_encode_cursor_is_valid_urlsafe_base64_of_key_sorted_json` and `test_handler_accepts_a_cursor_produced_by_encode_cursor`, assertions unchanged | unit | pytest | none | `uv run pytest tests/test_feed_cursor.py -q` | `uv run pytest tests/ -q` | repo root |
| AC6 | New near-miss shapes rejected; the handler maps rejection to 400 `invalid_cursor` with no DynamoDB call | T2; existing rejection tests in `tests/test_feed_cursor.py`; existing `test_handler_rejects_invalid_cursor_without_touching_dynamodb` | unit | pytest | none | `uv run pytest tests/test_feed_cursor.py -q` | `uv run pytest tests/ -q` | repo root |
| AC7 | One query per request in both directions; IAM unchanged | T3 (query count); existing `test_query_feed_issues_exactly_one_query_call`; existing `tests/test_infra_feed_api.py` unchanged and green; the PR's CI `cdk diff` shows no IAM change for `AiRadarFeedApi` (human reads it); live L5 | integration + synth | pytest + CDK assertions | none | `uv run pytest tests/test_infra_feed_api.py tests/test_feed_query.py -q` | `uv run pytest tests/ -q` | repo root |
| AC8 | Schema artifact equals the model; generated web types equal the artifact; the old suite is green; only `types.generated.ts` changed under `apps/web/` | No new test. Existing `test_committed_schema_artifact_matches_contracts_json_schema` and `apps/web` `types.generated.test.ts`; `git diff --stat -- apps/web` | unit | pytest; vitest | `uv run export_api_schema.py`; `npm run generate:types` | `uv run pytest tests/test_feed_api_contract.py tests/test_contracts_card.py -q`, then `npx vitest run features/feed/api/types.generated.test.ts` (cwd `apps/web`) | `uv run pytest tests/ -q && uv run ruff check . && uv run mypy .`; `npm run typecheck` (cwd `apps/web`) | repo root; `apps/web` |
| AC9 | The live check against the deployed API after merge and CI deploy | none (human-run runbook L1 to L6 below) | live | curl + jq | AWS credentials for `aws cloudformation describe-stacks`; the CI `backend deploy` run green | runbook L1 to L5 | L6 (full walk) | repo root |

Not tested on purpose: a `FeedResponse.prev_cursor` default test (a tautology, already shown by T3's null
assertion); IAM policy re-assertions (the existing infra test covers the unchanged template); a per-shape
handler 400 test (the mapping is one code path, already covered).

### Live verification runbook (human, after merge; not an executor task)
Run after the `backend deploy` run that includes `AiRadarFeedApi` is green, smoke included.

**Reminder: moto does not reproduce this.** moto returns a `LastEvaluatedKey` only when another item
follows. Real DynamoDB also returns one when a query stops at exactly `Limit`. T3 and T4 therefore cannot
catch a dangling `prev_cursor` on page 1 reached backward. Only the live check can, so L3 (and L6 at
`limit=1`) must confirm that `prev_cursor` is `null` on page 1 reached backward. A non-null value there
means the `limit + 1` read is missing or wrong, even if every offline test passes.
```bash
FEED_API_URL=$(aws cloudformation describe-stacks --stack-name AiRadarFeedApi --query "Stacks[0].Outputs[?OutputKey=='FeedApiUrl'].OutputValue" --output text)
P1=$(curl -s -G "$FEED_API_URL/v1/cards" --data-urlencode "limit=2")
echo "$P1" | jq '{ids: [.cards[].card_id], prev_cursor, has_next: (.next_cursor != null)}'
P2=$(curl -s -G "$FEED_API_URL/v1/cards" --data-urlencode "limit=2" --data-urlencode "cursor=$(echo "$P1" | jq -r .next_cursor)")
echo "$P2" | jq '{ids: [.cards[].card_id], prev_cursor}'
B1=$(curl -s -G "$FEED_API_URL/v1/cards" --data-urlencode "limit=2" --data-urlencode "cursor=$(echo "$P2" | jq -r .prev_cursor)")
diff <(echo "$P1" | jq -c '[.cards[].card_id]') <(echo "$B1" | jq -c '[.cards[].card_id]') && echo "L3 backward equals page 1"
echo "$B1" | jq .prev_cursor
F2=$(curl -s -G "$FEED_API_URL/v1/cards" --data-urlencode "limit=2" --data-urlencode "cursor=$(echo "$B1" | jq -r .next_cursor)")
diff <(echo "$P2" | jq -c '[.cards[].card_id]') <(echo "$F2" | jq -c '[.cards[].card_id]') && echo "L4 round trip"
TAG=$(echo "$P1" | jq -r '.cards[0].tags[0]')
T1=$(curl -s -G "$FEED_API_URL/v1/cards" --data-urlencode "limit=2" --data-urlencode "tag=$TAG")
T2=$(curl -s -G "$FEED_API_URL/v1/cards" --data-urlencode "limit=2" --data-urlencode "tag=$TAG" --data-urlencode "cursor=$(echo "$T1" | jq -r .next_cursor)")
echo "$T2" | jq '{ids: [.cards[].card_id], prev_cursor}'
curl -s -o /dev/null -w '%{http_code}\n' -G "$FEED_API_URL/v1/cards" --data-urlencode "limit=2" --data-urlencode "tag=$TAG" --data-urlencode "cursor=$(echo "$T2" | jq -r .prev_cursor)"
```
- **L1** `P1.prev_cursor` is `null`.
- **L2** `P2.prev_cursor` is non-null.
- **L3** `B1` has exactly `P1`'s ids in the same order, and `B1.prev_cursor` is `null` (option A of Q1).
- **L4** following `B1.next_cursor` returns `P2`'s ids.
- **L5** `T2.prev_cursor` is non-null, and the tag-filtered backward call prints `200`. If
  `T1.next_cursor` is `null`, pick a tag with more matches. No call in L1 to L5 returns 500, and the
  function's log group has no `AccessDeniedException` (AD-6 holds).
- **L6** (ties, recommended) walk the whole feed at `limit=1` forward, collecting ids, then walk back from
  the last page with `prev_cursor` until it is `null`. The backward ids, reversed, equal the forward ids,
  and the walk ends on the first card with `prev_cursor: null`, not on an extra empty page.

## Revision log
- Revision 1 (2026-11-10): first draft.
- Revision 2 (2026-11-10): Q1 option A and Q2 accept recorded; moto reminder added to the live runbook.

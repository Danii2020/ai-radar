# src/api — Plane B feed read API

Purpose: the Lambda behind `GET /v1/cards` (Phase 2, `feed-api`). It turns a request
(`tag`, `limit`, `cursor`) into one `Query` on the `feed-by-score` index and returns a
`FeedResponse` page with `next_cursor` and `prev_cursor`. Root guidance:
[`CLAUDE.md`](../../CLAUDE.md). The response contract lives in `src/contracts/card.py`.

## Key files

- `handler.py` — `handler(event, context)`, the API Gateway HTTP API (payload 2.0) entrypoint.
  It validates `limit` and the cursor, picks the direction from the cursor, and builds
  `prev_cursor` and `next_cursor` by the page rules. It emits no CORS headers, since API
  Gateway owns CORS. It logs one `feed_api_request` record per call.
- `cursor.py` — `encode_cursor(key, direction)` and `decode_cursor(token)`, the trust
  boundary. Forward with a key is the bare three-key object, byte-identical to cursors issued
  before backward paging. Backward with a key adds `"dir": "prev"`. Keyless
  `{"dir": "next"}` is start of feed, and `{"dir": "prev"}` is end of feed. Anything else
  raises `InvalidCursorError`, which the handler maps to 400 `invalid_cursor` before any
  DynamoDB call.
- `feed.py` — `query_feed(table, ...)`, one `Query` on `feed-by-score` with
  `Key("gsi_pk").eq("CARD")`. Forward uses `ScanIndexForward=False` and `Limit=limit`.
  Backward uses `ScanIndexForward=True` and `Limit=limit+1`, reverses the items into feed
  order, and drops the item furthest from the anchor. It returns `FeedPage`, and each card
  goes through `CardOut`. A malformed item is logged and skipped.
- `dynamo.py` — the only `boto3` site under `src/api/`. It holds the lazy resource singleton
  and re-exports `Attr` and `Key`.
- `config.py` — `CARD_TABLE_NAME`, the page-size settings, and the duplicated GSI name and
  partition (`FEED_GSI_NAME`, `FEED_GSI_PARTITION`). Plane B must not import Plane A, so the
  constants are copied, and a test keeps them equal to `curation/config.py`.

## Commands

```bash
uv run pytest tests/test_feed_cursor.py tests/test_feed_query.py tests/test_feed_api_handler.py
uv run pytest tests/test_feed_api_contract.py tests/test_infra_feed_api.py
uv run export_api_schema.py    # after any change to src/contracts/card.py (the schema artifact)
```

## Conventions

- Exactly one `Query` per request, on `feed-by-score`. No `Scan`, no second call and no
  draining loop. A filtered page may be short or empty while a cursor is still live.
- The cursor is the validation boundary. A decoded key reaches DynamoDB only after it passes
  the exact-shape check. Keep the forward encoding unchanged, because old `?cursor=` URLs
  must keep working.
- The IAM grant is index-only `dynamodb:Query` (AD-6). A backward request uses the same
  action, so the grant does not change. Do not widen it.
- Tests run offline with moto. moto returns no `LastEvaluatedKey` at exactly `Limit`, while
  real DynamoDB returns one, so only the live check can confirm the start-of-feed decision
  on real data.
- Dependencies come from the `api` dependency group in the `Dockerfile.feed_api` image. A
  module missing from that group passes pytest and fails in the built image, so import it
  inside the built container before trusting the group.

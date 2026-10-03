# Feed API Specification

> Last synced: 2026-09-17. Owned artifacts: `src/api/`, `src/contracts/card.py`,
> `infra/lib/feed_api.py`, `infra/stacks/feed_api_stack.py`,
> `docs/api/feed-api.v1.schema.json`.

## Purpose

Phase 2's read-only HTTP contract in front of the curated-cards table:
`GET /v1/cards`, its pagination/filter semantics, and the versioned
`CardOut`/`FeedResponse` schema future clients (the Next.js frontend, or any
other consumer) are built against. Its own capability because it is the
first genuinely external-facing contract in the project — a schema
mismatch here breaks callers outside this repo, unlike the internal
Protocol seams the other capabilities define.

## Requirements

### Requirement: FA-1 — Ordering via the feed-by-score index only

`GET /v1/cards` SHALL return cards in descending `gsi_sk` order (relevance
desc, then published desc) via exactly one `Query` against the
`feed-by-score` index (`card-persistence` PS-3) — never a `Scan`, and the
IAM role SHALL be structurally unable to perform one.

**Source:** feed-api · contract.md § Behavior Guarantees 1, 10

### Requirement: FA-2 — Tag filter without a second query

`?tag=X` SHALL restrict results to cards whose `tags` include `X`, applied
as a `FilterExpression` on the same query — no second index, no
post-hoc filtering, no extra AWS call.

**Source:** feed-api · contract.md § Behavior Guarantees 2

### Requirement: FA-3 — Cursor pagination round-trips exactly

`next_cursor` SHALL be an opaque, base64url-encoded, validated token; for
any fixed dataset and page size, concatenating pages obtained by following
`next_cursor` until `null` SHALL yield exactly the same card sequence, same
order, no duplicates, no omissions, as a single unpaginated query with the
same filter. A short or empty page with a non-null `next_cursor` SHALL NOT
be read as "end of feed" by a well-behaved client.

**Source:** feed-api · contract.md § Behavior Guarantees 4, 5, 6, 7, 8

#### Scenario: A tag has matches only on a later page
- **WHEN** a client requests `?tag=X&limit=5` and no card on the first page
  matches `X`
- **THEN** the response is `{"cards": [], "next_cursor": "<token>"}` (an
  empty page with a live cursor), not an end-of-results signal

### Requirement: FA-4 — Read-only IAM, no wildcard resource

The synthesized Lambda execution role SHALL contain no write action
(`PutItem`/`UpdateItem`/`DeleteItem`/`BatchWriteItem`/`Scan`/`BatchGetItem`),
no `bedrock:*`, no `secretsmanager:*`, no `Resource: "*"`, and no AWS
managed policy.

**Source:** feed-api · contract.md § Behavior Guarantees 10

### Requirement: FA-5 — CORS is an explicit allowlist

`AllowOrigins` SHALL equal a configured, explicit origin list — never `*` —
and `AllowMethods` SHALL be `["GET"]` only.

**Source:** feed-api · contract.md § Behavior Guarantees 12

## Invariants

1. `docs/api/feed-api.v1.schema.json` must equal `contracts.card.json_schema()`
   byte-for-byte after canonical JSON dumping — a drift is a test failure,
   preventing the API's generated-type consumers from silently diverging
   from the server (feed-api BG13).
2. A stored item that fails `CardOut` validation is logged and skipped, not
   fatal — the page still returns 200 with the remaining cards (feed-api BG9).

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| FA-R1 | Deployed function's `ReservedConcurrentExecutions` is `null` (unreserved), not the contract's intended `5` — bridged via `-c feed_api_reserved_concurrency=none` because this account's Lambda concurrency quota is still 10 (the same constraint `runtime-deployment` hit). Worth flipping back once the quota increases. | LOW (operational) | `README.md` "Phase 2 — Web Feed"; `specs/archived/feed-api/audit.md` AD-7 |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| feed-api | 2026-09-03 | `GET /v1/cards`, cursor pagination, tag filter, the `CardOut`/`FeedResponse` versioned contract, the `AiRadarFeedApi` CDK stack. Live-curl-verified 2026-09-04. |

## Related ADRs

None yet — shipped before `harny-adr` existed in this project.

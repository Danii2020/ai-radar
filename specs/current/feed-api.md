# Feed API Specification

> Last synced: 2026-11-10 (`feed-prev-cursor`: FA-7 added, FA-1 and FA-3 amended for backward pages, FA-R2 to FA-R4). Owned artifacts: `src/api/`, `src/contracts/card.py`, `scripts/ci/deploy_context.json` (the CORS origins, from the CI context),
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

*Amended by feed-prev-cursor (ADR 0051): a backward request (`prev_cursor`) reads the index in ascending order with one `Query`, then returns its page in the same descending order. The observable order above is unchanged.*

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

*Amended by feed-prev-cursor (AC3, ADR 0051): on a forward page, `next_cursor` is null if and only if DynamoDB returned no `LastEvaluatedKey`, as before. A page reached backward (`prev_cursor`) always has a non-null `next_cursor`, because it leads forward to the cards after that page (see FA-7).*

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

### Requirement: FA-6 — The CORS origins are the committed deploy context, and CI cannot silently revert them

The system SHALL take the feed API's allowed origins from `feed_api_allowed_origins` in the committed
`scripts/ci/deploy_context.json`, so a CI deploy of `AiRadarFeedApi` keeps the origin list the file holds. An
origin passed by hand is reverted by the next CI deploy. Each origin SHALL be `http://localhost:<port>` or an
`https://` URL with a host and no path, and a placeholder SHALL NOT be deployed.

**Source:** backend-cicd-pipeline · intent.md § AC15; execution-plan.md § Binding constraints (origin validation); ADR 0045 (capability `ci-cd`)

#### Scenario: A placeholder origin in the context file
- **WHEN** the context holds `https://<project>.vercel.app`
- **THEN** the origin validation fails the PR (offline: `tests/test_ci_deploy_context.py -k origin`). The value is
  `http://localhost:3000` today, the live value. The Vercel origin and its preflight check are pending
  (open item CICD-VERCEL in `ci-cd`; O12 i).

### Requirement: FA-7 — Backward paging with `prev_cursor`, and cursors issued earlier stay valid

`GET /v1/cards` SHALL return `prev_cursor` on every 200 response, next to `next_cursor`. `prev_cursor` SHALL be
`null` only on the first page of the feed (a request with no `cursor`, or one at the start of the feed), and a
non-null opaque token on every other page, including a page that is empty or short. Following `prev_cursor` SHALL
return the cards before that page in feed order, with no card skipped or repeated. A page reached backward SHALL
have a non-null `next_cursor`, and following it SHALL return the cards after that page with no gap and no repeat
(without a tag filter, exactly the page the client came from). A backward request SHALL make exactly one `Query`
on `feed-by-score`, with no change to the Lambda's IAM grant. A cursor issued before this change SHALL keep working
as a forward cursor and return the same page as before, and a forward `next_cursor` SHALL be the same bytes as
before. A cursor that is not one of the issued shapes SHALL return 400 `invalid_cursor` before any DynamoDB call.
The response contract stays `v1`: `prev_cursor` is an optional, nullable field.

**Source:** feed-prev-cursor · intent.md § AC1 to AC8; execution-plan.md § Binding constraints (page cursor rule table); ADR 0051, 0052, 0053, 0054

#### Scenario: Previous page from the second page
- **WHEN** a client follows the `prev_cursor` of the second page of `GET /v1/cards?limit=3`
- **THEN** the response carries the first page's cards in feed order, `prev_cursor: null`, and a non-null
  `next_cursor` that returns the second page

#### Scenario: A cursor issued before backward paging
- **WHEN** a client sends a forward cursor issued before this change
- **THEN** the response is the same page as before, with status 200

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
| FA-R2 | With a `tag` filter, backward page boundaries can differ from the forward pages, because DynamoDB applies the filter after `Limit`. The cards visited are the same. No over-fetch is added. Accepted by the human. | LOW (accepted) | `specs/archived/feed-prev-cursor/intent.md` AC4; ADR 0051 |
| FA-R3 | The live check (2026-11-10) ran a full walk at `limit=5` on a 16-card table, not the `limit=1` walk the runbook recommends. The tie groups (equal `gsi_sk`) in the live table were not recorded, so real-DynamoDB tie order is covered only by the forward and backward walks matching. The function was deployed by hand, not by CI. | LOW (open) | `specs/archived/feed-prev-cursor/audit.md` F5; `README.md` § Live state |
| FA-R4 | Audit round 1 findings left open, on record-keeping and test labels. T2's case `keyless-extra-key` does not test a keyless cursor with an extra key (F2). `tasks.md` has no recorded red results and a stale status (F3). The PR's CI and `cdk diff` have not run, because nothing is committed (F4). The T3 comment says relevance 5 where the data uses 9 (F6). Accepted as non-blocking in round 1. | LOW (open) | `specs/archived/feed-prev-cursor/audit.md` F2, F3, F4, F6 |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| feed-api | 2026-09-03 | `GET /v1/cards`, cursor pagination, tag filter, the `CardOut`/`FeedResponse` versioned contract, the `AiRadarFeedApi` CDK stack. Live-curl-verified 2026-09-04. |
| backend-cicd-pipeline | 2026-10-28 | FA-6: the allowed origins come from the committed deploy context (`http://localhost:3000`, the live value), validated, so a CI deploy does not revert them. Implemented and audit-approved with reservations; live since 2026-10-28 (two `backend deploy` runs on `main`, per the README). The Vercel origin and its preflight are pending (O12 i). |
| feed-prev-cursor | 2026-11-10 | FA-7: `prev_cursor` on every 200 and backward paging, with the direction carried in the opaque cursor and one reversed `Query` per request. FA-1 and FA-3 amended for backward pages. The optional response field keeps the schema at `v1`. Audit round 1 approved with reservations. Deployed by hand 2026-11-10 and live-checked at `limit=5`; not yet merged to `main`. |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| 0051 | Backward paging is one reversed Query, with the direction carried in the opaque cursor | Accepted |
| 0052 | The forward cursor encoding is frozen, so cursors issued earlier stay valid | Accepted |
| 0053 | The backward query reads limit + 1 items to tell the start of the feed from more before | Accepted |
| 0054 | An added optional response field does not bump the API version | Accepted |

ADRs 0051–0054 are from `feed-prev-cursor`. The original `feed-api` feature (2026-09-03) predates `harny-adr`, so it has no ADR. ADR 0045 belongs to `ci-cd`, not to this capability.

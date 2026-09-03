# Spec 01 — Feed read API

- **feature-name:** `feed-api`
- **SDD target dir:** `specs/feed-api/`
- **Depends on:** Phase 1's `dynamodb-card-store` (the `ai-radar-cards` table
  + `feed-by-score` GSI — already deployed, `AiRadarCardStore` stack)
- **Layer:** Data / infra

## Intent

Give the curated cards sitting in DynamoDB a real, public, read-only HTTP API
— **API Gateway + Lambda** — so a frontend (Spec 02) can render them. This is
the "API Gateway → Lambda → query DynamoDB" half of design §5's Plane B data
flow, and the first real consumer of the `feed-by-score` GSI that
`dynamodb-card-store` reserved specifically for this phase.

## Background

`ai-radar-cards` (see `specs/dynamodb-card-store/contract.md`) already has
every card written with:
- PK `card_id` (16-char sha256(url) prefix)
- `gsi_pk="CARD"` (constant, single partition), `gsi_sk=f"{relevance:03d}#{published}"`
  on the `feed-by-score` GSI, projection `ALL`
- Content attributes: `title`, `url`, `source`, `summary`, `tags` (L(S)),
  `type`, `relevance` (N), `published`, `takeaways` (L(S)), `created_at`,
  `updated_at`
- A reserved-but-unpopulated `embedding` attribute (Phase 3 — never read or
  written here)

`Card` today is a plain dataclass in `src/shared/cards.py` (see
`architecture-principles.md` boundary 2) — the trigger to promote it to a
versioned, validated (Pydantic) schema is exactly "when a real API exists,"
i.e. this spec.

## Scope

**In scope**
- A promoted `CardOut` (or similarly named) **Pydantic** schema — the API's
  response contract — derived from/matching the DynamoDB item shape above.
  Field-for-field parity with `Card`'s content attributes plus `card_id`,
  `created_at`, `updated_at`. Lives somewhere both this Lambda and (later)
  the frontend's typed-client generation can reference — architect decides
  exact module location per `architecture-principles.md`'s "shared contract"
  guidance, but it must **not** live inside `src/curation/` or force Plane A
  to import it.
- A Lambda handler (Python) that:
  - Queries `feed-by-score` (`Key("gsi_pk").eq("CARD")`), sorted descending
    by `gsi_sk` (highest relevance/most recent first) — `ScanIndexForward=False`.
  - Supports an optional `tag` query parameter — applied as a
    **`FilterExpression`** on the same query (no new index; see the phase
    README's scoping decision).
  - Supports cursor pagination: an opaque, base64-or-similar-encoded
    `LastEvaluatedKey` passthrough as a `cursor` query param in/out. A
    `limit` query param (bounded, sane default and max — e.g. default 20,
    max 100).
  - Returns `{"cards": [CardOut, ...], "next_cursor": str | null}`.
  - Read-only: no write path, no dependency on Plane A's summarize/discover
    code.
- API Gateway (HTTP API, not REST API — cheaper, simpler) fronting the
  Lambda, with **CORS restricted to the deployed frontend origin(s)**
  (configurable, not `*`).
- IAM: a least-privilege execution role scoped to `dynamodb:Query` on the
  `ai-radar-cards` table's `feed-by-score` index ARN only — no `PutItem`,
  no `Scan`, no wildcard resource. Mirror the least-privilege pattern
  `runtime-packaging`'s `AgentRuntimeStack` already established.
- CDK construct (`infra/lib/feed_api.py`) + stack
  (`infra/stacks/feed_api_stack.py`), wired into `infra/app.py`, following
  the exact `lib/<name>.py` construct + `stacks/<name>_stack.py` pattern
  Phase 1 established (see `infra/lib/agent_runtime.py` /
  `infra/stacks/agent_runtime_stack.py` for precedent). Reads the table name
  from the existing `AiRadarCardStore` stack's output/export — **does not**
  redefine or duplicate the table.
- Packaging decision: `pydantic` is a project dependency but is **not** part
  of the default Lambda Python runtime — the architect must pick a bundling
  approach (e.g. `aws_cdk.aws_lambda_python_alpha`'s `PythonFunction` for
  auto-dependency-bundling, or a Docker-image Lambda, or a manually built
  Lambda layer) and record the tradeoff. Prefer whichever keeps the existing
  `uv`-based dependency story intact rather than a second, parallel
  packaging mechanism.
- Tests against `moto`-backed DynamoDB (mirroring `dynamodb-card-store`'s
  test approach) plus handler-level unit tests (query building, pagination
  cursor encode/decode, tag filter, CORS headers) — no real AWS calls in the
  automated suite.

**Out of scope**
- The frontend / any UI (Spec 02).
- Auth (Phase 2 scoping decision: none — public read API).
- Any write path back to `ai-radar-cards` — Plane A owns all writes.
- A dedicated tag-indexed GSI — filtering is a `FilterExpression` on the
  existing query until scale demands otherwise (see phase README).
- A per-card detail/permalink endpoint — the list endpoint is the whole API
  surface for Phase 2.

## Contract sketch

```python
class CardOut(BaseModel):           # promoted, versioned Card API contract
    card_id: str
    title: str
    url: str
    source: str
    summary: str
    tags: list[str]
    type: str
    relevance: int
    published: str
    takeaways: list[str] = []
    created_at: str
    updated_at: str

class FeedResponse(BaseModel):
    cards: list[CardOut]
    next_cursor: str | None

def handler(event, context) -> dict:  # API Gateway HTTP API proxy integration
    """GET /cards?tag=<str>&limit=<int>&cursor=<str> -> FeedResponse (as JSON, with CORS headers)."""
```

## Acceptance criteria

- [ ] `GET /cards` returns cards sorted by relevance/date (highest/most
      recent first), matching the `feed-by-score` GSI's `gsi_sk` ordering.
- [ ] `?tag=<x>` filters to cards whose `tags` list contains `<x>`, applied
      via `FilterExpression` against the same GSI query (no new index).
- [ ] `?limit=<n>` bounds the page size (sane default + max enforced
      server-side, not just documented).
- [ ] `?cursor=<token>` round-trips: the `next_cursor` from one response,
      passed as `cursor` on the next request, continues from exactly where
      the previous page left off, with no duplicate or skipped cards across
      pages (verified against a seeded multi-page dataset in the moto test).
- [ ] The Lambda's IAM role permits `dynamodb:Query` on the `feed-by-score`
      index only — verified by asserting the synthesized CDK template has no
      `Resource: "*"` and no write actions (mirrors Spec 03/04's IAM
      assertions).
- [ ] CORS headers on every response are scoped to the configured frontend
      origin(s), not `*`.
- [ ] Deployed and curl-verified against the **real** `ai-radar-cards` table
      (not just moto) — a real HTTPS request returns real cards.
- [ ] `uv run pytest tests/` stays green with the new suite, no real-AWS
      calls in the automated tests.

## SDD note

Feed to `sdd-architect` as `feed-api`. The contract must lock: (1) the
`CardOut`/`FeedResponse` schema shape — this becomes Spec 02's typed-client
target, so treat it as load-bearing; (2) the pagination cursor encoding
(opaque to the client, but its round-trip behavior is a hard guarantee);
(3) the Lambda packaging approach for `pydantic` (flag it as an explicit
architecture decision in contract.md, not an implementation afterthought).

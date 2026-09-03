# Intent: feed-api

## Problem Statement

Phase 1 ended with cards landing in DynamoDB unattended. Nobody can *see*
them. The only readers of `ai-radar-cards` today are `aws dynamodb scan
--select COUNT` in a runbook and the CloudWatch log record
`curation_run_complete` — i.e. the product's entire output is currently
visible only to an operator with AWS credentials and a terminal.

Design §8's Phase 2 deliverable is *"I can open a URL and see them."* The
frontend that does that (Spec 02, `web-feed-ui`) cannot talk to DynamoDB from
a browser, and per the phase README's scoping decision it must not: the read
path belongs behind a real, versioned HTTP contract that any client can
consume, not inside a Next.js server component holding AWS credentials.

This spec builds that read path: **API Gateway (HTTP API) → Lambda →
`dynamodb:Query` on the `feed-by-score` GSI**, returning a sorted, tag-
filterable, cursor-paginated page of cards as JSON.

Two things make it more than "add a Lambda":

1. **`feed-by-score` has never been read.** `dynamodb-card-store` flagged it
   as a *deliberate speculative index* built for exactly this phase and wrote
   `gsi_pk`/`gsi_sk` on every card since, but no production code has ever
   queried it. This spec is that index's first real consumer, and the first
   chance to find out whether its key design actually serves the feed.
2. **`Card` must be promoted.** `architecture-principles.md` boundary 2 names
   the trigger by name: *"When the frontend or a real API exists, promote it
   to a versioned, validated schema (Pydantic) shared as the API contract."*
   A real API now exists. That promotion is the one deliberate cross-plane
   artifact of Phase 2, and it becomes Spec 02's typed-client target — so its
   shape is load-bearing, not cosmetic.

Who is affected: the human who wants to read their own feed (today: nobody
can); Spec 02, which is blocked on a real URL and real response shapes; and
Phase 3's chat UI, which will reuse the same deployment pattern for its own
endpoint.

## Goals

1. **A deployed, public, read-only HTTP endpoint** — `GET /v1/cards` on an
   API Gateway **HTTP API** (not REST API) fronting a Python Lambda — that
   returns cards from `ai-radar-cards` ordered by descending relevance then
   descending publish date, i.e. the `feed-by-score` GSI's native
   `ScanIndexForward=False` order. No scans, no client-side sorting.
2. **Promote `Card` to a versioned, validated Pydantic schema** (`CardOut` /
   `FeedResponse`) in a module neither plane owns internals of, exported as a
   checked-in **JSON Schema artifact** so Spec 02 generates its TypeScript
   types from a real file instead of transcribing prose. Plane A's
   `shared.cards.Card` dataclass is **not** modified and does not import it.
3. **Tag filtering via `FilterExpression`** on the same single GSI query —
   no new index, no backfill, no second access pattern (phase README scoping
   decision).
4. **Cursor pagination with a hard round-trip guarantee**: an opaque token
   wrapping DynamoDB's `LastEvaluatedKey`, such that following `next_cursor`
   until it is `null` yields every matching card exactly once, in order, with
   no duplicates and no gaps. The encoding is opaque to clients; the
   *behavior* is a contract.
5. **Least-privilege IAM in the Phase 1 house style** — a hand-authored
   `iam.Role` with explicit `PolicyStatement`s (never `grant_*()`, never a
   managed policy): `dynamodb:Query` on the `feed-by-score` index ARN, and
   `logs:CreateLogStream`/`PutLogEvents` on this function's own log group.
   No write action anywhere, no `Resource: "*"` anywhere.
6. **CORS scoped to a configured origin list, never `*`**, owned by the API
   Gateway CORS configuration and changeable per-deploy with `cdk deploy -c`
   (Spec 02 supplies the real Vercel origin later).
7. **One explicit, justified packaging decision for `pydantic`** — it is a
   project dependency but not part of the Lambda runtime — that keeps `uv` +
   `uv.lock` the single source of dependency truth and does **not** make
   `uv run pytest tests/` require Docker or network.
8. **CDK construct + stack in the established pattern**
   (`infra/lib/feed_api.py` → `infra/stacks/feed_api_stack.py` →
   `infra/app.py`), referencing the already-deployed `ai-radar-cards` table
   by name — never redefining it.
9. **Really deploy it and really curl it**: a real HTTPS request against the
   real table returning real cards, plus a real cursor round trip and a real
   tag filter, recorded in the README runbook alongside teardown.

## Success Criteria

- [ ] `GET /v1/cards` returns `{"cards": [...], "next_cursor": ...}` with
      cards ordered by descending `gsi_sk` (relevance desc, then published
      desc) — asserted against a seeded `moto` table and observed in the live
      curl.
- [ ] `?tag=<x>` returns only cards whose `tags` list contains `<x>`, applied
      as a `FilterExpression` on the same `Key("gsi_pk").eq("CARD")` query —
      the synthesized IAM policy and the query both prove no second index is
      involved.
- [ ] `?limit=<n>` is enforced server-side: absent → 20; a value outside
      `[1, 100]` or not an integer → HTTP 400, never a silent full-table read.
- [ ] **Cursor round trip**: over a seeded multi-page dataset, walking
      `next_cursor` until it is `null` yields exactly the same card sequence
      as one unpaginated query — no duplicates, no gaps — including when a
      `tag` filter is applied and a page comes back short.
- [ ] A malformed/tampered `cursor` returns HTTP 400 `invalid_cursor`; it is
      never silently ignored (silently restarting pagination would duplicate
      cards) and never reaches DynamoDB.
- [ ] The synthesized template contains **no** `Resource: "*"`, **no**
      `dynamodb:PutItem`/`UpdateItem`/`DeleteItem`/`BatchWriteItem`/`Scan`,
      and **no** AWS managed policy on the function's role.
- [ ] `CorsConfiguration.AllowOrigins` is the configured origin list and does
      not contain `*`; the origin list is changeable in exactly one place
      (a module-level default, overridable with `cdk deploy -c`).
- [ ] The stack creates **no** DynamoDB table (`resource_count_is(
      "AWS::DynamoDB::Table", 0)`) — the RETAINed Phase 1 table is referenced
      by name only.
- [ ] A checked-in JSON Schema artifact for `CardOut`/`FeedResponse` exists
      and a test fails if it drifts from the Pydantic models.
- [ ] `uv run pytest tests/` is green, 100% offline: no real AWS calls, no
      network, **and no Docker daemon required for synth** (verified: image
      assets are built by the CDK CLI at deploy time, not during
      `Template.from_stack`).
- [ ] **Live**: `curl "$FEED_API_URL/v1/cards?limit=2"` against the deployed
      stack returns real cards from `ai-radar-cards`; a second curl with the
      returned `next_cursor` returns the next distinct page; `?tag=<real tag>`
      narrows the result set.
- [ ] `git diff` shows **zero** changes under `src/curation/`,
      `src/shared/`, `runtime_app.py`, `Dockerfile`, and the four existing
      `infra/lib/*.py` / `infra/stacks/*.py` pairs.

## Non-Goals

- **Any write path.** Plane A owns every write to `ai-radar-cards`. This
  Lambda's role cannot write, by construction.
- **Auth.** Public read API (phase README scoping decision) — the content is
  public AI-news summaries. No JWT authorizer, no API key, no usage plan.
- **A tag-indexed GSI.** Filtering stays a `FilterExpression` until the
  corpus makes that painful (phase README).
- **A per-card detail/permalink endpoint, a `/tags` endpoint, or any second
  route.** `GET /v1/cards` is the entire API surface for Phase 2.
- **The frontend** (Spec 02) — including hosting, rendering, and the real
  Vercel origin value.
- **Chat / RAG / Bedrock of any kind.** This Lambda makes zero model calls
  and needs zero Bedrock permissions.
- **Reading or writing the reserved `embedding` attribute** (Phase 3). It is
  deliberately excluded from the query's `ProjectionExpression`.
- **A domain layer.** Per `architecture-principles.md`, a read API over one
  index is not a `Card` lifecycle, not users-as-entities, and not model
  tension — no aggregates, repositories, domain events, or service layer. A
  handler + a query function + a schema module is the whole design.
- **Custom metrics / EMF / alarms for the API.** `run-observability` already
  costs ~$1.20/mo in custom metrics; API Gateway and Lambda emit built-in
  CloudWatch metrics for free and that is enough for Phase 2.
- **A custom domain name, WAF, CloudFront, or caching layer.** (WAF is
  deferred behind an explicit revisit trigger — see the cost-discipline
  constraint below.)
- **Modifying `shared.cards.Card`.** The dataclass Plane A renders and
  persists stays exactly as-is; `CardOut` is a *read-side projection of the
  stored item*, not a rename.

## Constraints

- **The table and its GSI are already deployed and RETAINed.** `ai-radar-cards`
  (PK `card_id`) + `feed-by-score` (`gsi_pk="CARD"`, `gsi_sk=f"{relevance:03d}#{published}"`,
  projection `ALL`) exist with real data. `specs/dynamodb-card-store/contract.md`
  calls the key schema LOCKED — this spec reads it and must not propose a
  change to it.
- **`pydantic` is not in the Lambda Python runtime** and `pydantic-core` is a
  compiled, platform-specific wheel — the local macOS `.venv` cannot simply be
  zipped. A bundling mechanism is mandatory, and it must not fork the `uv` +
  `uv.lock` dependency story into a second one (no `requirements.txt` checked
  in, no `pip`).
- **Offline test suite is non-negotiable.** Every existing CDK test uses
  `Template.from_stack` with no credentials and no network
  (`tests/test_infra*.py`). Any packaging choice that makes synth require a
  Docker daemon (e.g. `aws_lambda_python_alpha.PythonFunction`'s bundling)
  would break `uv run pytest tests/` on a machine without Docker running.
  *Verified this session:* a `DockerImageFunction` asset synthesizes fine with
  the Docker daemon **unavailable** — the CLI builds it at deploy time.
- **API Gateway owns CORS, not the Lambda.** AWS docs are explicit: *"If you
  configure CORS for an API, API Gateway ignores CORS headers returned from
  your backend integration."* Emitting `Access-Control-Allow-Origin` from the
  handler would be dead code.
- **`FilterExpression` is applied after `Limit`.** *Verified against `moto`
  this session:* a query with `Limit=2` and a tag filter returned **1** item
  and still carried a `LastEvaluatedKey`. Short pages are normal and must not
  be treated by clients (or by Spec 02) as "end of feed".
- **DynamoDB numbers come back as `Decimal`** (resource API). `relevance` must
  be coerced to `int` — *verified:* pydantic 2.13.4 coerces `Decimal("7") →
  7` and rejects `Decimal("7.5")`.
- **Index-only IAM is a deploy-time unknown.** Whether `dynamodb:Query`
  scoped to the index ARN alone suffices (vs. also needing the base-table ARN)
  is not settled by AWS docs; the community record is contradictory. It must
  therefore be a single, one-line-changeable constant with the fallback
  documented, and the live curl is the verification — the same treatment
  `eventbridge-schedule` gave its universal-target service id.
- **Cost discipline ($500 credits).** HTTP API ($1.00/M requests) + Lambda +
  on-demand DynamoDB reads at personal-feed traffic is effectively $0, but the
  endpoint is **public and unauthenticated**, so a runaway or looping client is
  the only real cost risk. Stage-level throttling (20 rps / 40 burst) and
  reserved concurrency (5) are required guards, not polish — but be precise
  about what they do and do not cover:
  - **Covered (compute):** throttled requests are rejected at the API Gateway
    edge, so a flood cannot multiply Lambda invocations, Lambda GB-seconds, or
    DynamoDB read units. Backend spend is hard-capped.
  - **NOT covered (request-count billing):** API Gateway bills *requests
    received*, and a 429 is still a billed request (verified against AWS
    pricing docs/community guidance, Aug 2026). A client stuck in an
    indefinite retry loop keeps accruing $1.00/M even while being throttled.
    At that rate it takes ~10⁷ requests to reach even $10, so this is a slow
    leak, not a cliff.
  - **Backstop for the uncovered part:** the already-deployed `AiRadarBudget`
    stack (Phase 1, `run-observability`) alerts by SNS email at $50/$100/$250
    of account spend. That is the intended detector for request-count-driven
    cost, which is why this spec adds no alarm of its own.
  - **Revisit trigger (deferred, not forgotten):** if API-Gateway
    request-count spend ever shows up as a real, non-trivial line in Cost
    Explorer / the Budget (distinct from Lambda and DynamoDB spend), add an
    **AWS WAF rate-based rule** (per-source-IP cap) at that point. It is
    excluded today because its ~$5–6/mo *fixed* cost exceeds the risk it
    mitigates for a single-user feed at an unpublished URL — the same
    "defer until a real trigger fires" discipline this project applies to the
    vector store (design §) and to `architecture-principles.md`'s DDD
    triggers. Per-user rate limiting is impossible without identity, and
    introducing identity would reverse this phase's explicit "no auth"
    scoping decision.

  No new recurring cost class is introduced (no NAT, no OpenSearch, no
  provisioned capacity, no WAF).
- **CDK version is pinned at `aws-cdk-lib==2.261.0`**, where
  `aws_cdk.aws_apigatewayv2` and `aws_cdk.aws_apigatewayv2_integrations` are
  **stable** (verified in the installed package — no alpha module needed for
  the API; the alpha `aws-lambda-python-alpha` module is deliberately avoided).
- **Plane separation.** The API is Plane B. It must not import `src/curation/`
  (Plane A internals), and Plane A must not import it. Shared literals that
  must agree across the boundary (`feed-by-score`, `"CARD"`) are duplicated
  deliberately and guarded by a drift test — the same remedy
  `tests/test_infra_agent_runtime.py::test_infra_and_app_sentinel_literals_match`
  applies to the Tavily sentinel.

## Prior Art

- **`specs/dynamodb-card-store/contract.md`** — the LOCKED key schema, the
  item attribute table, the `Decimal` note, the reserved-word placeholders
  (`#t`/`#u`/`#src`/`#ty`), and the *already-written* Phase 2 query
  (`IndexName="feed-by-score"`, `Key("gsi_pk").eq("CARD")`,
  `ScanIndexForward=False`) that this spec implements for real.
- **`src/curation/dynamo.py`** — the shape of what is actually stored (source
  of truth for `CardOut`'s fields), plus the lazy-singleton boto3 resource and
  injectable-`client` constructor style this spec copies so tests can inject
  `moto`.
- **`infra/lib/agent_runtime.py` + `infra/stacks/agent_runtime_stack.py`** —
  the construct-exposes-attributes → stack-wraps-plus-`CfnOutput` → flat-module
  `sys.path` app pattern, and the explicit-`PolicyStatement` least-privilege
  style (never `grant_*()`, wildcards named and justified one at a time).
- **`infra/lib/curation_schedule.py`** — the "one place to change it,
  overridable with `cdk deploy -c`" convention for deploy-time knobs, and the
  precedent for pinning a fact that only a live fire can confirm.
- **`tests/test_infra_agent_runtime.py`** — the synth-only assertion helpers
  (`_resources_of_type`, `_statement_by_sid`, "the only wildcard is X") and the
  cross-boundary literal drift test this spec reuses in shape.
- **`tests/conftest.py` + `tests/test_dynamo_store.py`** — the `moto`-backed
  `dynamo_resource`/`dynamo_table` fixtures (already creating the exact
  `feed-by-score` GSI) that this spec's query tests extend, and the
  "zero real-AWS calls" rule.
- **`src/curation/config.py` / `src/shared/config.py`** — the
  `pydantic-settings` + module-level UPPERCASE constants config idiom, and the
  "fixed constants deliberately outside the settings model" convention.
- **`Dockerfile` + `tests/test_dockerfile.py`** — the `uv sync --frozen`,
  no-pip, no-`requirements.txt`, ARM64 image idiom and the functional
  Dockerfile regression test this spec mirrors for `Dockerfile.feed_api`.
- **README.md's Phase 1 runbooks** — the deploy → verify → teardown structure
  (including "what this costs while it is up") that this spec extends.
- **External (verified 2026-08-30):** AWS *Configure CORS for HTTP APIs*
  (API Gateway ignores backend CORS headers); AWS *Lambda proxy integrations
  for HTTP APIs* (payload format 2.0 event/response shape, comma-joined
  duplicate query params); `aws-cdk-lib` 2.261.0 `aws_apigatewayv2`,
  `aws_apigatewayv2_integrations`, `aws_lambda`, `aws_ecr_assets` (synth-probed
  in-process this session); `boto3` 1.43.56 + `moto` 5.x GSI query behavior
  (pagination keys, filter-after-limit, `ProjectionExpression` coexisting with
  a `boto3.dynamodb.conditions` filter).

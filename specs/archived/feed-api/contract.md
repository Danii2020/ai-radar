# Contract: feed-api

> **Language / stack.** Backend Python 3.11+ managed by `uv` (`pyproject.toml`
> + `uv.lock`, `[tool.uv] package = false`, `src/` layout). Infra is **CDK v2
> in Python** (`aws-cdk-lib==2.261.0`), same `infra/lib/<name>.py` construct +
> `infra/stacks/<name>_stack.py` stack + `infra/app.py` wiring as Phase 1.
> Tests are `pytest` + `moto` + `aws_cdk.assertions.Template`. No TypeScript
> in this spec — the Next.js client is Spec 02 (`web-feed-ui`), which consumes
> the JSON Schema artifact this spec publishes.
>
> **New code lives under `src/api/` (Plane B serving) and `src/contracts/`
> (the published `Card` contract).** Nothing under `src/curation/` or
> `src/shared/` is modified, and neither imports the new packages. `boto3` is
> confined to `src/api/dynamo.py` exactly as Plane A confines it to
> `src/curation/dynamo.py`.

## AWS / library API surface (verified — do not trust memory)

Verified **2026-08-30** against the installed `aws-cdk-lib==2.261.0`,
`boto3==1.43.56`, `moto>=5.2.2`, `pydantic==2.13.4` (in-process synth/query
probes), plus AWS docs for API Gateway HTTP APIs.

### DynamoDB feed query (boto3 resource API)

```python
import boto3
from boto3.dynamodb.conditions import Attr, Key

table = boto3.resource("dynamodb").Table("ai-radar-cards")

resp = table.query(
    IndexName="feed-by-score",
    KeyConditionExpression=Key("gsi_pk").eq("CARD"),
    FilterExpression=Attr("tags").contains("llm"),          # only when ?tag= given
    ProjectionExpression=(
        "card_id, #t, #u, #src, summary, tags, #ty, relevance, "
        "published, takeaways, created_at, updated_at"
    ),
    ExpressionAttributeNames={"#t": "title", "#u": "url", "#src": "source", "#ty": "type"},
    ScanIndexForward=False,                                  # relevance desc, then date desc
    Limit=20,
    ExclusiveStartKey={"card_id": "…", "gsi_pk": "CARD", "gsi_sk": "004#2026-08-04"},
)
resp["Items"]                    # list[dict]; numbers are Decimal
resp.get("LastEvaluatedKey")     # absent on the last page
```

Facts established by running this against `moto` (not from memory):

| Fact | Evidence |
|---|---|
| `LastEvaluatedKey` for a GSI query has **exactly three** keys — `card_id`, `gsi_pk`, `gsi_sk` (all `S`) | probe returned `{'card_id': 'id4', 'gsi_pk': 'CARD', 'gsi_sk': '004#2026-08-04'}` |
| `FilterExpression` is applied **after** `Limit` | `Limit=2` + tag filter returned **1** item **and** a `LastEvaluatedKey` |
| The last page carries **no** `LastEvaluatedKey` | full query (`Limit=10`, 6 items) → key absent |
| A hand-written `ProjectionExpression` + `ExpressionAttributeNames` **coexists** with a `boto3.dynamodb.conditions` filter (boto3 merges its generated `#n0…` placeholders with ours) | probe succeeded; `embedding` correctly absent from the returned item |
| `relevance` deserializes as `Decimal` | `type(item["relevance"]) is decimal.Decimal` |

> **Reserved words.** `url` and `type` are DynamoDB reserved words; `title`
> and `source` are aliased defensively for symmetry with
> `src/curation/dynamo.py`'s `#t`/`#u`/`#src`/`#ty` placeholders. Every
> declared name **must** be referenced by the expression or DynamoDB rejects
> the request.

> **Why `ProjectionExpression` at all** (the GSI already projects `ALL`): it
> excludes the reserved `embedding` attribute. Phase 3 will write a 256-float
> vector per card; without this projection every feed page would silently pay
> for and transfer ~4 KB/card of vector data. This is a forward-looking cost
> guard, not premature optimization.

### Pydantic (2.13.4)

```python
from pydantic import BaseModel, ConfigDict, Field

CardOut.model_validate(dynamo_item)   # Decimal("7") -> 7; Decimal("7.5") -> ValidationError
FeedResponse(...).model_dump_json()   # canonical JSON body
CardOut.model_json_schema()           # the artifact Spec 02 generates TS types from
```

### API Gateway HTTP API — payload format 2.0 (AWS docs, verified)

Event keys used by this handler (all others ignored):

```python
event["queryStringParameters"]                 # dict[str, str]; ABSENT when no query string
event["requestContext"]["http"]["method"]      # "GET"
event["rawPath"]                               # "/v1/cards"
```

Duplicate query params are **comma-joined** into one string in 2.0 (there is
no `multiValueQueryStringParameters`). Response shape returned by the handler
(explicit, never relying on API Gateway's inference):

```python
{"statusCode": 200, "headers": {"content-type": "application/json"}, "body": "<json>"}
```

CDK synth facts (probed in-process, no AWS calls):

| Fact | Value |
|---|---|
| `HttpLambdaIntegration` default payload format | `PayloadFormatVersion: "2.0"` |
| Route resource | `RouteKey: "GET /v1/cards"`, `AuthorizationType: "NONE"` |
| CORS | `CorsConfiguration: {AllowOrigins: [...], AllowMethods: ["GET"], AllowHeaders: ["content-type"], MaxAge: 3600}` |
| Default stage | `StageName: "$default"`, `AutoDeploy: true`; `DefaultRouteSettings` set via the `CfnStage` escape hatch |
| `DockerImageFunction` | `PackageType: "Image"`, `Architectures: ["arm64"]`; **synthesizes with no Docker daemon running** — the image is built by the CDK CLI at deploy time |

> **CORS ownership (AWS doc quote).** *"If you configure CORS for an API, API
> Gateway ignores CORS headers returned from your backend integration."* — the
> handler therefore emits **no** CORS headers; API Gateway's
> `CorsConfiguration` is the single source of truth, and the synth test is the
> real assertion.

## Architecture decisions

### AD-1 — Lambda packaging for `pydantic`: **Docker-image Lambda built with `uv`** (DECIDED)

`pydantic` is a project dependency but not in the Lambda Python runtime, and
`pydantic-core` is a compiled, platform-specific wheel — the macOS `.venv`
cannot be zipped. Options considered:

| Option | Verdict |
|---|---|
| **`aws_lambda_python_alpha.PythonFunction`** | **Rejected.** (a) It is an *alpha* module that must be version-locked to `aws-cdk-lib` exactly, and its API is explicitly unstable. (b) Its bundling runs **during synth**, so `Template.from_stack` in `tests/test_infra_feed_api.py` would need a running Docker daemon — breaking the repo's "pytest is 100% offline, no credentials, no daemons" rule that every Phase 1 infra test depends on. |
| **Hand-built Lambda layer / zip** (`uv export` + `uv pip install --target --python-platform aarch64-manylinux…`) | **Rejected.** Docker-free and uv-native, but it needs a build artifact to exist on disk *before* synth (pytest included), which means either a synth-time `subprocess`/network call (breaks offline tests) or a manual pre-`cdk deploy` build step plus fixture directories in tests — a second, hand-rolled packaging mechanism to maintain. |
| **Docker-image Lambda** (`lambda_.DockerImageFunction` + `DockerImageCode.from_image_asset`) | **CHOSEN.** |

Why it wins on this repo's own criteria:

1. **One dependency story.** The image installs from `pyproject.toml` +
   `uv.lock` via `uv` — the exact idiom the existing root `Dockerfile`
   already uses for the AgentCore agent. No `requirements.txt` is checked in,
   no `pip`, no second mechanism.
2. **Offline tests stay offline.** *Verified this session:* a stack containing
   `DockerImageFunction` synthesized to a complete template with the Docker
   daemon unavailable (`docker info` non-zero). Image assets are recorded in
   the cloud assembly and built by the **CDK CLI at deploy time**, so
   `uv run pytest tests/` needs neither Docker nor network.
3. **No alpha CDK modules.** `aws_apigatewayv2` and `aws_lambda` are stable in
   the pinned 2.261.0.
4. **Repo precedent + ARM64.** Same `--platform=linux/arm64` Graviton choice as
   the AgentCore image (cheaper per GB-s, native build on the dev Mac).

Accepted costs, stated up front: `cdk deploy` requires a running container
engine (Docker 28.3.3 is installed on the dev machine); the image asset lands
in the CDK bootstrap ECR repo (`cdk-hnb659fds-container-assets-*`, pennies/month
at this size); cold start is a few hundred ms worse than a slim zip
(irrelevant for a personal feed, and the image is deliberately kept small — see
AD-2).

### AD-2 — The image installs an `api` dependency group only (DECIDED)

A new `[dependency-groups] api = ["pydantic>=2.13"]` in `pyproject.toml`,
installed with `uv export --frozen --only-group api …`. The Lambda must **not**
carry `langgraph`, `bedrock-agentcore`, `tavily-python`, `feedparser`, or
`rich` — none are used by the read path, and they would multiply image size
and cold start for nothing. `boto3` is **not** installed: the AWS base image
`public.ecr.aws/lambda/python:3.12` ships the SDK, exactly like the managed
runtime.

`pydantic` becomes an explicit group member rather than relying on its current
transitive presence via `pydantic-settings`.

### AD-3 — `src/api/config.py` does **not** import `shared.config` (DECIDED)

Every other config module in the repo imports `shared.config` for
`AWS_REGION` and its one `load_dotenv()` side effect. The Lambda deliberately
does not, because:

- In Lambda, `AWS_REGION` is set by the runtime and picked up by `boto3`'s
  default chain — the API never needs to name a region.
- There is no `.env` in the image (`.dockerignore` excludes it, by design),
  so `load_dotenv()` would be dead weight at every cold start, and pulling
  `python-dotenv` + the whole cross-plane knob set (`FEEDS`, model IDs, cache
  paths) into a read API is noise.

`src/api/config.py` is therefore a self-contained `pydantic-settings` module in
the same idiom (private `_ApiSettings`, module-level UPPERCASE public surface,
explicit `validation_alias` per field).

### AD-4 — Cross-plane literals are duplicated, then drift-tested (DECIDED)

`"feed-by-score"` and `"CARD"` exist in `src/curation/config.py`. Plane B must
not import Plane A (`architecture-principles.md` boundary 1), so `src/api/config.py`
re-declares them and `tests/test_feed_api_contract.py` asserts the two are
equal — the identical remedy already used for the Tavily sentinel
(`tests/test_infra_agent_runtime.py::test_infra_and_app_sentinel_literals_match`,
finding F10). The CDK construct duplicates them a third time (infra is a
separate toolchain, as `infra/lib/agent_runtime.py` documents) and its synth
test asserts the ARN it builds ends in `/index/feed-by-score`.

### AD-5 — `CardOut` lives in `src/contracts/`, not `src/api/` (DECIDED)

`architecture-principles.md` boundary 2 points at `packages/contracts` in the
future monorepo layout; `src/contracts/` is that package's in-repo ancestor.
Keeping the schema out of `src/api/` matters because Spec 02 generates its
TypeScript types from this module's JSON Schema artifact — it should not have
to reach into a package that also holds HTTP wiring, boto3 calls, and Lambda
config. Plane A does **not** import `src/contracts/`; `shared.cards.Card` is
untouched. Versioning is expressed three ways, all in one place: the route
(`/v1/cards`), the constant `CARD_SCHEMA_VERSION = "v1"`, and the artifact
filename `docs/api/feed-api.v1.schema.json`.

### AD-6 — IAM scoped to the index ARN, with a documented one-line fallback (DECIDED)

The role grants `dynamodb:Query` on
`arn:aws:dynamodb:us-east-1:536697225154:table/ai-radar-cards/index/feed-by-score`
only. Whether index-only is sufficient (vs. also needing the base-table ARN)
is **not** settled by AWS documentation, and the community record is
contradictory — so, exactly like `eventbridge-schedule`'s universal-target
service id, it is a single module-level constant with the fallback written
down: if the live curl returns `AccessDeniedException`, add the base-table ARN
to the *same* statement (still `Query`-only, still no wildcard) and redeploy.
The live curl is the verification.

### AD-7 — Public endpoint guards: stage throttling + reserved concurrency (DECIDED)

The endpoint is unauthenticated by scoping decision, so an abusive or looping
client is the only realistic way this spec touches the $500 budget. Two cheap
bounds, both asserted in synth tests: `DefaultRouteSettings`
`{ThrottlingRateLimit: 20, ThrottlingBurstLimit: 40}` on the `$default` stage,
and `reserved_concurrent_executions=5` on the function. Neither costs anything;
both hard-cap **compute** spend — a flood is rejected at the API Gateway edge
and cannot multiply Lambda invocations, GB-seconds, or DynamoDB read units.

> **Known limitation — accepted, not solved.** These guards do **not** cap API
> Gateway's own per-request billing. API Gateway bills *requests received*, and
> a throttled `429` is still a billed request (verified against AWS pricing
> docs/community guidance, Aug 2026), so a client in an indefinite retry loop
> keeps accruing $1.00/M while being throttled. There is no per-user rate limit
> available without identity, and adding identity would reverse the phase's
> "no auth" scoping decision.
>
> Mitigations considered and **rejected for Phase 2**: an **AWS WAF rate-based
> rule** (the real per-source-IP fix, but ~$5–6/mo *fixed* — more than the risk
> it removes for a single-user feed at an unpublished URL, and WAF is already
> an explicit Non-Goal), and an **API Gateway usage plan + API key** (no WAF
> cost, but the "key" would ship in public client-side JS, so it stops
> accidental runaway clients rather than deliberate abuse, while softly
> reversing the "no auth" decision).
>
> **Backstop:** the already-deployed `AiRadarBudget` stack's $50/$100/$250 SNS
> alerts (Phase 1, `run-observability`) — which is why this spec adds no alarm
> or metric of its own. **Revisit trigger:** if API-Gateway request-count spend
> becomes a real, non-trivial line in Cost Explorer / the Budget (distinct from
> Lambda and DynamoDB spend), add the WAF rate-based rule *then*. Same
> "defer until a trigger fires" discipline as the vector-store deferral and
> `architecture-principles.md`'s DDD triggers. This spec adds **no** WAF, **no**
> API key, and **no** new resource for this — it documents the tradeoff only.

> **Deploy-time environmental constraint, discovered live (2026-09-02) — not a
> design change.** The first real `cdk deploy AiRadarFeedApi` against this AWS
> account failed: the account's Lambda **"Concurrent executions"** quota was
> **10**, not AWS's stated default of 1000, and CDK's synthesized
> `reserved_concurrent_executions=5` was rejected because reserving 5 would
> drop the account's *unreserved* concurrency below AWS's required floor of
> 10. A quota increase to 1001 was requested (AWS Support case
> `178836416700301`; pending, no ETA) — self-service Service Quotas requests
> for this quota are rejected outright when the requested value is not above
> 1000, so "just ask for slightly more than 10" is not an available path.
> `infra/lib/feed_api.py` gained a `reserved_concurrent_executions: int | None
> = DEFAULT_RESERVED_CONCURRENCY` constructor kwarg (default unchanged — the
> audited AD-7 baseline is still 5) and `FeedApiStack` reads it from a new CDK
> context key, `feed_api_reserved_concurrency`, the same one-line-flip pattern
> AD-6 already established for `grant_base_table_query`. `cdk deploy
> AiRadarFeedApi -c feed_api_reserved_concurrency=none` omits the reservation
> (leaving the function's concurrency unreserved) for exactly the deploys that
> need it to unblock account provisioning; a plain `cdk deploy AiRadarFeedApi`
> with no override restores 5 with zero code change. This flag exists purely
> to bridge an account-provisioning gap, not to relax AD-7's intent — it
> should be removed or ignored once the quota increase is confirmed.

## Interfaces

### `src/contracts/card.py` — CREATE (the published contract)

```python
"""Versioned, validated `Card` API contract (Phase 2, spec `feed-api`).

Promotes `shared.cards.Card` (a plain dataclass, Plane A's internal type) to
the published, versioned schema `architecture-principles.md` boundary 2 calls
for once a real API exists. This module is the ONLY definition of the feed
API's response shape; `docs/api/feed-api.v1.schema.json` is generated from it
and is what `web-feed-ui` (Spec 02) generates TypeScript types from.

Plane A does not import this module and `shared.cards.Card` is unchanged: a
`CardOut` is a READ-SIDE PROJECTION of a stored DynamoDB item (Card content
fields + `card_id` + `created_at`/`updated_at`), not a rename of the dataclass.
Changing a field here is a BREAKING API change — bump the version.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

#: Bumped only on a breaking change to CardOut/FeedResponse. Mirrored by the
#: route prefix (`/v1/cards`) and the schema artifact filename.
CARD_SCHEMA_VERSION: str = "v1"


class CardOut(BaseModel):
    """One curated card, as returned by `GET /v1/cards`.

    Field-for-field parity with the DynamoDB item written by
    `curation.dynamo.DynamoCardStore.upsert` (see
    specs/dynamodb-card-store/contract.md "Item schema"), minus the internal
    index keys `gsi_pk`/`gsi_sk` and the Phase-3-reserved `embedding`.
    """

    model_config = ConfigDict(extra="ignore")

    card_id: str        # sha256(url)[:16] — the table PK, stable per URL
    title: str
    url: str
    source: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    type: str           # "paper" | "release" | "project" | "news" | "concept" (not enforced)
    relevance: int      # 1-10; stored as N, arrives as Decimal, coerced here
    published: str      # ISO date "YYYY-MM-DD", or "" when the source had none
    takeaways: list[str] = Field(default_factory=list)
    created_at: str     # ISO8601 UTC, set once by Plane A
    updated_at: str     # ISO8601 UTC, advances on every re-curation


class FeedResponse(BaseModel):
    """One page of the feed. `next_cursor` is opaque: pass it back verbatim as
    `?cursor=`. It is `None` — and ONLY None — when the feed is exhausted."""

    model_config = ConfigDict(extra="ignore")

    cards: list[CardOut]
    next_cursor: str | None = None


def json_schema() -> dict:
    """The published JSON Schema artifact (`$defs`-linked CardOut inside
    FeedResponse). Written to docs/api/feed-api.v1.schema.json by
    `export_api_schema.py`; a test fails if the file drifts from this."""
    return FeedResponse.model_json_schema()
```

`type` is a plain `str`, deliberately **not** an `Enum`: the value comes from
an LLM (`Card.from_model` defaults to `"news"`), and a card whose type the
model invented must render, not 500. Same reasoning for `relevance` being an
unbounded `int` rather than `conint(ge=1, le=10)`.

### `src/api/config.py` — CREATE

```python
class _ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    card_table_name: str = Field("ai-radar-cards", validation_alias="CARD_TABLE_NAME")
    default_page_size: int = Field(20, validation_alias="FEED_API_DEFAULT_PAGE_SIZE")
    max_page_size: int = Field(100, validation_alias="FEED_API_MAX_PAGE_SIZE")


_settings = _ApiSettings()

CARD_TABLE_NAME: str = _settings.card_table_name
DEFAULT_PAGE_SIZE: int = _settings.default_page_size
MAX_PAGE_SIZE: int = _settings.max_page_size

# Fixed constants — NOT env-overridable, deliberately outside the model.
# DUPLICATED from curation/config.py because Plane B must not import Plane A
# (architecture-principles boundary 1); tests/test_feed_api_contract.py asserts
# the two stay equal (AD-4).
FEED_GSI_NAME: str = "feed-by-score"
FEED_GSI_PARTITION: str = "CARD"
```

### `src/api/cursor.py` — CREATE (the pagination contract)

```python
"""Opaque pagination cursor: base64url(JSON(LastEvaluatedKey)).

The ENCODING is an implementation detail clients must not parse. The
ROUND TRIP is a hard contract (see Behavior Guarantees 5-8).
"""

#: The exact key set a `feed-by-score` query's LastEvaluatedKey carries
#: (verified against moto). Anything else is a tampered/foreign cursor.
CURSOR_KEYS: frozenset[str] = frozenset({"card_id", "gsi_pk", "gsi_sk"})


class InvalidCursorError(ValueError):
    """Raised for any cursor that is not a well-formed, in-partition key."""


def encode_cursor(last_evaluated_key: dict) -> str:
    """`{"card_id": …, "gsi_pk": "CARD", "gsi_sk": …}` -> URL-safe base64 of its
    compact, key-sorted JSON, with `=` padding stripped. Deterministic: the
    same key always yields the same token."""


def decode_cursor(token: str) -> dict:
    """Inverse of `encode_cursor`. Re-pads, base64url-decodes, JSON-parses, and
    VALIDATES: a JSON object whose keys are exactly CURSOR_KEYS, all values
    `str`, and `gsi_pk == config.FEED_GSI_PARTITION`. Anything else (bad
    base64, bad JSON, wrong/missing keys, non-str value, foreign partition)
    raises InvalidCursorError. Never returns a partially-trusted dict — the
    decoded value is passed straight to DynamoDB as ExclusiveStartKey, so this
    IS the trust boundary."""
```

### `src/api/dynamo.py` — CREATE (the only boto3 site in `src/api/`)

```python
def card_table(client=None):
    """The `ai-radar-cards` Table resource. `client` is an optional boto3
    DynamoDB **ServiceResource** (tests inject a `moto`-backed one); when None a
    lazily-created singleton `boto3.resource("dynamodb")` is used — region comes
    from the Lambda runtime env via boto3's default chain (AD-3). Mirrors
    `curation.dynamo`'s lazy-singleton + injectable-client pattern."""
```

### `src/api/feed.py` — CREATE (query + projection, no HTTP)

```python
@dataclass(frozen=True)
class FeedPage:
    """Result of one DynamoDB query: validated cards + the raw
    LastEvaluatedKey (None on the last page) + how many stored items failed
    CardOut validation and were skipped."""

    cards: list[CardOut]
    last_evaluated_key: dict | None
    skipped: int


def query_feed(
    table,
    *,
    tag: str | None = None,
    limit: int = 20,
    exclusive_start_key: dict | None = None,
) -> FeedPage:
    """ONE `Query` against the `feed-by-score` GSI —
    `KeyConditionExpression=Key("gsi_pk").eq(FEED_GSI_PARTITION)`,
    `ScanIndexForward=False`, `Limit=limit`, the pinned `ProjectionExpression`,
    plus `FilterExpression=Attr("tags").contains(tag)` when `tag` is a
    non-empty string and `ExclusiveStartKey` when a cursor was supplied.

    Exactly one query per call: no draining loop, no follow-on read. A filtered
    page may therefore be short or empty while `last_evaluated_key` is not None
    (DynamoDB applies the filter after `Limit`) — that is expected, contractual
    behavior, not an error.

    Per-item resilience: an item that fails `CardOut.model_validate` is logged,
    counted in `skipped`, and omitted — one malformed row never fails the page
    (repo house rule; mirrors `DynamoCardStore.upsert`'s per-card try/except).
    """
```

### `src/api/handler.py` — CREATE (the Lambda entrypoint)

```python
def handler(event: dict, context) -> dict:
    """`GET /v1/cards?tag=<str>&limit=<int>&cursor=<str>` (API Gateway HTTP API,
    payload format 2.0) -> a `FeedResponse` JSON body.

    200 body: {"cards": [CardOut, ...], "next_cursor": str | null}
    400 body: {"error": "<code>", "message": "<human-readable>"}
    500 body: {"error": "internal_error", "message": "internal error"}

    Emits NO CORS headers — API Gateway owns CORS and ignores backend CORS
    headers (see AD / pinned surface above). Logs one structured
    `feed_api_request` record per request (`json.dumps`, same idiom as
    `runtime_app.py`'s `curation_run_complete`).
    """
```

Parameter parsing rules (all enforced server-side, in this order):

| Param | Absent | Valid | Invalid |
|---|---|---|---|
| `tag` | no filter | any non-empty string → `contains` on `tags`, **exact, case-sensitive** | `""` (or whitespace-only) is treated as absent, not as an error |
| `limit` | `DEFAULT_PAGE_SIZE` (20) | integer in `[1, MAX_PAGE_SIZE]` | non-integer or outside the range → **400 `invalid_limit`** (never clamped silently, never a full read) |
| `cursor` | start of feed | a token produced by `encode_cursor` | **400 `invalid_cursor`** — never ignored, never forwarded to DynamoDB |

Tag matching is exact and case-sensitive because the filter runs inside
DynamoDB against stored values; normalizing the input could not match
differently-cased stored tags without rewriting the data. Spec 02 must send
tags exactly as they appear in card payloads (which is where it gets them).

### `Dockerfile.feed_api` — CREATE (repo root; build context = repo root)

```dockerfile
# Feed API Lambda image (Phase 2, spec `feed-api`). Build context is the repo
# root; `.dockerignore` (shared with the AgentCore image) already excludes
# `.env`, `.venv/`, `cdk.out/`, `tests/`, `infra/`, `docs/`.
FROM --platform=linux/arm64 public.ecr.aws/lambda/python:3.12

# uv is the ONLY installer — no pip, no requirements.txt in the repo (AD-1/AD-2).
COPY --from=ghcr.io/astral-sh/uv:0.7.17 /uv /usr/local/bin/uv

# Dependency layer: pyproject.toml + uv.lock only, resolved from the lockfile.
# `--only-group api` installs pydantic and nothing else; boto3 ships in the AWS
# base image, exactly as in the managed runtime.
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-emit-project --only-group api -o /tmp/requirements.txt \
 && uv pip install --no-cache --target "${LAMBDA_TASK_ROOT}" -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# App code. `src/` is not an installed package (`[tool.uv] package = false`);
# copying the two needed packages INTO ${LAMBDA_TASK_ROOT} (already on
# sys.path) means no sys.path insert is needed, unlike the repo's other
# entrypoints. src/curation and src/shared are deliberately NOT copied.
COPY src/api/ ${LAMBDA_TASK_ROOT}/api/
COPY src/contracts/ ${LAMBDA_TASK_ROOT}/contracts/

CMD ["api.handler.handler"]
```

### `infra/lib/feed_api.py` — CREATE (CDK construct)

```python
"""Reusable CDK construct: the feed read API (Phase 2, spec `feed-api`).

`infra/lib/` — NOT `infra/constructs/` — a local `constructs` package on
`sys.path` would shadow the CDK `constructs` library.
"""

# --- The "one place" for the deploy-time knobs -----------------------------
# Override per-deploy with `cdk deploy -c feed_api_allowed_origins=...`
# (see FeedApiStack). NEVER "*" — a synth test asserts that.
DEFAULT_ALLOWED_ORIGINS = ["http://localhost:3000"]   # Spec 02 adds the Vercel origin
DEFAULT_THROTTLE_RATE = 20      # req/s, steady state (AD-7)
DEFAULT_THROTTLE_BURST = 40
DEFAULT_RESERVED_CONCURRENCY = 5
DEFAULT_MEMORY_MB = 512
DEFAULT_TIMEOUT = Duration.seconds(10)
DEFAULT_LOG_RETENTION = logs.RetentionDays.ONE_MONTH

# Same literals as src/api/config.py and src/curation/config.py — infra is a
# separate toolchain (different sys.path/dependency group), so they are
# duplicated by convention, exactly like agent_runtime.py's Tavily sentinel.
CARD_TABLE_NAME = "ai-radar-cards"
FEED_GSI_NAME = "feed-by-score"
ROUTE_PATH = "/v1/cards"


class FeedApi(Construct):
    """HTTP API -> Lambda -> Query(feed-by-score). Exposes `.http_api`,
    `.function`, `.log_group`, `.role` for the stack to CfnOutput.

    The `ai-radar-cards` table is REFERENCED by name (deployed and RETAINed by
    AiRadarCardStore, no cross-stack export) — never created or imported as a
    CFN resource. The permission-policy ARNs use the LITERAL pinned account +
    region for exactly that reason, matching `agent_runtime.py`.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        account: str = "536697225154",
        region: str = "us-east-1",
        card_table_name: str = CARD_TABLE_NAME,
        feed_gsi_name: str = FEED_GSI_NAME,
        allowed_origins: list[str] | None = None,
        grant_base_table_query: bool = False,   # AD-6 fallback: one-line flip
    ) -> None: ...
```

Resources it creates, in order:

1. **`logs.LogGroup`** `"/aws/lambda/ai-radar-feed-api"`,
   `retention=ONE_MONTH`, `removal_policy=DESTROY` — created explicitly so the
   role's `logs` grant can be scoped to it (and so retention is not infinite).
2. **`iam.Role`** assumed by `lambda.amazonaws.com`, **no managed policies**
   (`AWSLambdaBasicExecutionRole` is deliberately not attached — it allows
   `logs:*` on `*`), with exactly two statements:

   ```python
   iam.PolicyStatement(
       sid="FeedGsiQuery",
       effect=iam.Effect.ALLOW,
       actions=["dynamodb:Query"],
       resources=[f"arn:aws:dynamodb:{region}:{account}:table/{card_table_name}/index/{feed_gsi_name}"],
       # + f"arn:aws:dynamodb:{region}:{account}:table/{card_table_name}" IFF
       #   grant_base_table_query (AD-6 fallback, still Query-only)
   )
   iam.PolicyStatement(
       sid="FeedApiLogsWrite",
       effect=iam.Effect.ALLOW,
       actions=["logs:CreateLogStream", "logs:PutLogEvents"],
       resources=[f"{self.log_group.log_group_arn}:*"],
   )
   ```

3. **`lambda_.DockerImageFunction`** — `function_name="ai-radar-feed-api"`,
   `code=DockerImageCode.from_image_asset(<repo root>, file="Dockerfile.feed_api",
   platform=ecr_assets.Platform.LINUX_ARM64)`,
   `architecture=lambda_.Architecture.ARM_64`, `role=<the role above>`,
   `log_group=<the log group above>`, `memory_size=512`,
   `timeout=Duration.seconds(10)`,
   `reserved_concurrent_executions=5`,
   `environment={"CARD_TABLE_NAME": card_table_name}`.
   The asset directory is resolved as `Path(__file__).parents[2]` (repo root)
   so it is identical under `cdk` and under `pytest`.
4. **`apigwv2.HttpApi`** — `api_name="ai-radar-feed-api"`, `cors_preflight=
   CorsPreflightOptions(allow_origins=<configured>, allow_methods=[CorsHttpMethod.GET],
   allow_headers=["content-type"], max_age=Duration.hours(1))`, then
   `add_routes(path="/v1/cards", methods=[HttpMethod.GET],
   integration=HttpLambdaIntegration("FeedIntegration", fn))`. No `$default`
   route: any other path/method is a 404 from API Gateway.
5. **Throttling** on the auto-created `$default` stage via the typed escape
   hatch:

   ```python
   cfn_stage = self.http_api.default_stage.node.default_child
   cfn_stage.default_route_settings = apigwv2.CfnStage.RouteSettingsProperty(
       throttling_rate_limit=DEFAULT_THROTTLE_RATE,
       throttling_burst_limit=DEFAULT_THROTTLE_BURST,
   )
   ```

### `infra/stacks/feed_api_stack.py` — CREATE

```python
class FeedApiStack(Stack):
    """Wraps `FeedApi`. Reads the allowed-origin list from CDK context so
    Spec 02 can redeploy with the real Vercel origin without a code edit:
    `cdk deploy -c feed_api_allowed_origins=https://ai-radar.vercel.app`
    (comma-separated for several)."""

    def __init__(self, scope, construct_id, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        raw = self.node.try_get_context("feed_api_allowed_origins")
        origins = [o.strip() for o in raw.split(",") if o.strip()] if raw else None
        api = FeedApi(self, "FeedApi", allowed_origins=origins)
        CfnOutput(self, "FeedApiUrl", value=api.http_api.api_endpoint)
        CfnOutput(self, "FeedApiFunctionName", value=api.function.function_name)
        CfnOutput(self, "FeedApiLogGroupName", value=api.log_group.log_group_name)
        CfnOutput(self, "FeedApiAllowedOrigins", value=",".join(api.allowed_origins))
```

### `infra/app.py` — MODIFY (one import + one line)

```python
from stacks.feed_api_stack import FeedApiStack  # noqa: E402
...
FeedApiStack(app, "AiRadarFeedApi")  # NEW (Phase 2, spec 01)
```

### `export_api_schema.py` — CREATE (repo root, matching `run_*.py` convention)

```python
"""Write the published feed-API JSON Schema artifact.

    uv run export_api_schema.py     # -> docs/api/feed-api.v1.schema.json

Spec 02 (`web-feed-ui`) generates its TypeScript types from that file.
`tests/test_feed_api_contract.py` fails if the committed file drifts from
`contracts.card.json_schema()`, so regenerating is a required step whenever
CardOut/FeedResponse changes (which is a BREAKING API change — bump
CARD_SCHEMA_VERSION and the route/artifact version).
"""
```

### `pyproject.toml` — MODIFY (append one dependency group)

```toml
[dependency-groups]
api = ["pydantic>=2.13"]     # Lambda image contents (AD-2); resolved into uv.lock
```

`uv add --group api pydantic` (never `pip`); `uv.lock` is regenerated and
committed.

### `.env.example` — MODIFY (append)

```bash
# Feed read API (Phase 2, spec `feed-api`). Only CARD_TABLE_NAME is set on the
# deployed Lambda; the page-size bounds are here for local/test overrides.
# FEED_API_DEFAULT_PAGE_SIZE=20
# FEED_API_MAX_PAGE_SIZE=100
```

## Data Models

### HTTP surface

| Method + path | Query params | 200 body |
|---|---|---|
| `GET /v1/cards` | `tag` (str, optional) · `limit` (int, 1-100, default 20) · `cursor` (opaque str, optional) | `FeedResponse` |

```jsonc
// 200
{
  "cards": [
    {
      "card_id": "0a1b2c3d4e5f6071",
      "title": "…",
      "url": "https://…",
      "source": "Tavily: example.com",
      "summary": "…",
      "tags": ["llm", "agents"],
      "type": "news",
      "relevance": 8,
      "published": "2026-08-29",
      "takeaways": ["…", "…"],
      "created_at": "2026-08-29T06:00:03.114512+00:00",
      "updated_at": "2026-08-30T06:00:04.882301+00:00"
    }
  ],
  "next_cursor": "eyJjYXJkX2lkIjoiMGExYjJjM2Q0ZTVmNjA3MSIsImdzaV9wayI6IkNBUkQiLCJnc2lfc2siOiIwMDgjMjAyNi0wOC0yOSJ9"
}

// 400
{"error": "invalid_limit", "message": "limit must be an integer between 1 and 100"}
```

### Mapping: DynamoDB item → `CardOut`

| DynamoDB attribute | `CardOut` field | Transform |
|---|---|---|
| `card_id` (S) | `card_id` | identity |
| `title`/`url`/`source`/`summary`/`type`/`published`/`created_at`/`updated_at` (S) | same | identity |
| `tags` / `takeaways` (L(S)) | same | identity; missing → `[]` |
| `relevance` (N) | `relevance` (`int`) | `Decimal` → `int` (pydantic coercion) |
| `gsi_pk` / `gsi_sk` (S) | — | internal index keys, **not** projected, **not** returned |
| `embedding` (L(N), Phase 3) | — | excluded by `ProjectionExpression` |

## State Changes

None to any existing runtime state. This spec adds a **read-only** consumer of
`ai-radar-cards`; Plane A's graph, nodes, state, store, and schedule are
untouched. The only new persistent AWS state is the API Gateway HTTP API, the
Lambda function + its log group, the IAM role, and the CDK ECR image asset —
all owned by the new `AiRadarFeedApi` stack and all destroyed by
`cdk destroy AiRadarFeedApi` (the RETAINed table survives, by design).

## Behavior Guarantees

1. **Ordering.** `GET /v1/cards` returns cards in descending `gsi_sk` order
   (relevance desc, then published desc) — exactly one
   `Query(IndexName="feed-by-score", KeyConditionExpression=Key("gsi_pk").eq("CARD"),
   ScanIndexForward=False)` per request. No `Scan` is ever issued (and the IAM
   role could not perform one).
2. **Tag filter.** With `?tag=X`, every returned card satisfies `X in
   card.tags`, and the filter is a `FilterExpression` on the same query — no
   second index, no post-hoc filtering in the handler, no extra AWS call.
3. **Page size.** `len(cards) <= limit` always; `limit` defaults to 20 and can
   never exceed `MAX_PAGE_SIZE` (100) — a request outside `[1, 100]` is
   rejected with 400 rather than served.
4. **Short pages are legal.** `cards` may be shorter than `limit`, or empty,
   while `next_cursor` is non-`null` (DynamoDB filters after `Limit`). A client
   must paginate until `next_cursor is null`; "fewer than `limit`" never means
   "end of feed".
5. **Cursor opacity.** `next_cursor` is `base64url(JSON(LastEvaluatedKey))`
   with padding stripped; clients must treat it as opaque. It is `null` **iff**
   DynamoDB returned no `LastEvaluatedKey`.
6. **Cursor round trip (the load-bearing one).** For any fixed dataset and any
   `limit`, concatenating the pages obtained by following `next_cursor` until
   it is `null` yields **exactly** the same card sequence, in the same order,
   as a single unpaginated query with the same `tag` — no duplicate
   `card_id`, no omitted `card_id`. Verified against a seeded multi-page
   `moto` dataset, both unfiltered and filtered.
7. **Cursor validation.** `decode_cursor` accepts only a JSON object whose keys
   are exactly `{card_id, gsi_pk, gsi_sk}`, all `str`, with
   `gsi_pk == "CARD"`. Anything else raises `InvalidCursorError` → HTTP 400,
   and no DynamoDB call is made. A cursor cannot be used to steer the query at
   another partition or another index.
8. **Encode/decode is an exact inverse.** `decode_cursor(encode_cursor(k)) == k`
   for every well-formed `LastEvaluatedKey`, and `encode_cursor` is
   deterministic (key-sorted, compact JSON) — the same key always produces the
   same token.
9. **Per-item resilience.** A stored item that fails `CardOut` validation is
   logged and skipped; the page still returns 200 with the remaining cards
   (house rule: one bad item never kills a run). The skip count appears in the
   request log record, not in the response body (the response shape is locked
   for Spec 02).
10. **No writes, ever.** The synthesized role contains no
    `dynamodb:PutItem`/`UpdateItem`/`DeleteItem`/`BatchWriteItem`/`Scan`/
    `BatchGetItem`, no `bedrock:*`, no `secretsmanager:*`, **no
    `Resource: "*"`**, and no AWS managed policy. The Lambda cannot mutate
    `ai-radar-cards` even if the handler tried.
11. **No table creation.** `AiRadarFeedApi` synthesizes zero
    `AWS::DynamoDB::Table` / `AWS::DynamoDB::GlobalTable` resources — the
    Phase 1 table is referenced by name only.
12. **CORS.** `CorsConfiguration.AllowOrigins` equals the configured origin
    list, never contains `*`, and `AllowMethods` is `["GET"]` only. The handler
    emits no CORS headers (API Gateway would ignore them).
13. **Contract artifact parity.** `docs/api/feed-api.v1.schema.json` equals
    `contracts.card.json_schema()` byte-for-byte after canonical JSON dumping;
    a drift is a test failure, so Spec 02's generated types cannot silently
    diverge from the server.
14. **Plane separation holds.** `src/api/` and `src/contracts/` import nothing
    from `src/curation/`; `src/curation/` and `src/shared/` import nothing from
    them; `boto3` appears in `src/api/` only in `dynamo.py`. Asserted by an AST
    import test, mirroring `test_boto3_import_confined_to_dynamo_module`.
15. **Offline tests.** Every new test runs with no credentials, no network, and
    **no Docker daemon**: DynamoDB via `moto.mock_aws`, infra via
    `Template.from_stack` (image assets are built by the CDK CLI at deploy
    time, not at synth).

## Error Handling Contract

| Error condition | Behavior | User impact |
|---|---|---|
| `limit` absent | use `DEFAULT_PAGE_SIZE` (20) | first 20 cards |
| `limit` not an integer, `< 1`, or `> 100` | **400** `{"error":"invalid_limit"}`; no AWS call | explicit message naming the bound |
| `cursor` malformed (bad base64/JSON), wrong key set, non-`str` value, or `gsi_pk != "CARD"` | **400** `{"error":"invalid_cursor"}`; no AWS call | client restarts pagination deliberately, rather than silently re-reading page 1 (which would duplicate cards) |
| `tag` empty/whitespace-only | treated as absent (no filter) | full feed |
| `tag` matches nothing | **200** with `{"cards": [], "next_cursor": …}` | empty state, not an error (Spec 02 renders "no matches") |
| One stored item fails `CardOut` validation | log + `skipped += 1` + omit; page still 200 | one card missing; feed still renders |
| Every item on a page is filtered out by DynamoDB | 200, `cards: []`, `next_cursor` non-null | client follows the cursor (Guarantee 4) |
| DynamoDB throttling / `ResourceNotFoundException` / credential error | log with stack trace, **500** `{"error":"internal_error","message":"internal error"}` — the exception text is never echoed to the client | generic error; the detail is in CloudWatch |
| Any unexpected exception in the handler | same as above — the handler never raises out of `handler()` (an unhandled raise would surface API Gateway's own opaque 502) | consistent JSON error shape |
| Request to any other path/method (e.g. `POST /v1/cards`, `GET /`) | API Gateway 404 `{"message":"Not Found"}` — no `$default` route exists | nothing reaches the Lambda |
| Browser request from a non-allowed origin | API Gateway omits `Access-Control-Allow-Origin`; the browser blocks the read | Spec 02 must be deployed at an allow-listed origin |
| `AccessDeniedException` on the live query (AD-6 risk) | not handled in code — it is a deploy-time misconfiguration; fix is `grant_base_table_query=True` and redeploy | surfaced loudly by the runbook's curl, before Spec 02 depends on it |

## Dependencies

- **Internal (new, created here):** `src/contracts/card.py`, `src/api/{config,cursor,dynamo,feed,handler}.py`.
- **Internal (read-only reference, never imported by app code):**
  `src/curation/config.py` — only `tests/test_feed_api_contract.py` imports it,
  to assert the duplicated GSI literals match (AD-4).
- **Internal (unchanged, not imported):** everything else under
  `src/curation/` and `src/shared/`; `shared.cards.Card` in particular.
- **External (runtime, new group `api`):** `pydantic>=2.13` (installed into the
  Lambda image). `boto3` comes from the AWS base image, not the lockfile.
- **External (dev, existing):** `pytest`, `moto>=5.2.2`.
- **External (infra, existing):** `aws-cdk-lib>=2.261.0` (`aws_apigatewayv2`,
  `aws_apigatewayv2_integrations`, `aws_lambda`, `aws_ecr_assets`, `aws_iam`,
  `aws_logs` — all **stable**, no alpha packages), `constructs>=10.7.1`.
- **Toolchain (deploy only):** a running container engine for
  `cdk deploy AiRadarFeedApi` (image asset build). Not needed for `cdk synth`
  or `pytest`.

## Integration Points

- **`dynamodb-card-store` (Phase 1, deployed)** — this spec is the
  `feed-by-score` GSI's first real consumer. It reads the exact key schema that
  contract locked and adds no attribute, no index, and no write path. The
  table's `RemovalPolicy.RETAIN` is unaffected.
- **`runtime-packaging` / `eventbridge-schedule` (Phase 1, deployed)** —
  untouched. The curation agent keeps writing while the API reads; concurrent
  writes are safe (see the honest limitation below).
- **`web-feed-ui` (Spec 02, not started)** — consumes `FeedApiUrl` (the
  `CfnOutput`), `GET /v1/cards`, and `docs/api/feed-api.v1.schema.json`. Spec 02
  closes the CORS loop by redeploying this stack with
  `-c feed_api_allowed_origins=<real Vercel origin>`; no code change here.
- **Phase 3 (RAG chat)** — will add its own endpoint; the `embedding`
  attribute it populates is deliberately excluded from this query's projection,
  so a populated vector costs the feed nothing.
- **`AiRadarBudget` (Phase 1)** — the existing budget/SNS alarms cover this
  spend too; no new alert threshold and no new metric are introduced.

> **Honest limitation (documented, accepted).** Cursor pagination is keyed on
> `gsi_sk`, which Plane A rewrites when a card's `relevance` or `published`
> changes on re-curation. If a daily curation run lands mid-pagination, a card
> can in principle be seen twice or missed across pages. At one write burst per
> day against a read-mostly personal feed this is acceptable; the alternative
> (a snapshot/consistent-read design) is not worth its complexity in Phase 2.

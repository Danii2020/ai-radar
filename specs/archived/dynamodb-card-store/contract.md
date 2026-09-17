# Contract: dynamodb-card-store

> All new runtime code lives under `src/curation/` alongside Specs 01–02. It
> **imports** (never forks) `RawItem` from `spike.feeds`, `Card` from
> `spike.cards`, the `CardStore` Protocol from `curation.interfaces`, and
> `AWS_REGION` from `spike.config`. New config knobs extend the existing
> `src/curation/config.py` (created by Spec 02) — they are **added**, not a new
> module, and `src/spike/config.py` is left untouched. `src/curation/interfaces.py`
> (the `CardStore` Protocol) is the stable seam and is **not modified**. The CDK
> app lives under a new top-level `infra/` directory. Import style matches the
> spike (`from spike.X import Y` once `src/` is on `sys.path`).

## AWS / library API surface (pinned via Context7 — do not trust memory)

Verified 2026-07-20. boto3 `/boto/boto3`; CDK `/websites/aws_amazon_cdk_api_v2_python`.

### boto3 DynamoDB (resource API — `boto3.resource("dynamodb")`)

The store uses the **resource** abstraction (`Table`), which marshals native
Python types (and requires `Decimal` for numbers — see note). Signatures relied on:

```python
import boto3
from boto3.dynamodb.conditions import Key

resource = boto3.resource("dynamodb", region_name="us-east-1")
table = resource.Table("ai-radar-cards")

# Idempotent upsert of one card (SET all content fields; preserve created_at;
# advance updated_at; NEVER touch `embedding`). No ConditionExpression needed —
# PK-keyed update_item is insert-or-replace by definition.
table.update_item(
    Key={"card_id": "0a1b2c3d4e5f6071"},
    UpdateExpression=(
        "SET #t=:t, #u=:u, source=:src, summary=:sum, tags=:tags, "
        "#ty=:ty, relevance=:rel, published=:pub, takeaways=:tk, "
        "gsi_pk=:gpk, gsi_sk=:gsk, updated_at=:now, "
        "created_at=if_not_exists(created_at, :now)"
    ),
    ExpressionAttributeNames={
        "#t": "title", "#u": "url", "#ty": "type",  # reserved words / clarity
    },
    ExpressionAttributeValues={
        ":t": "…", ":u": "…", ":src": "…", ":sum": "…", ":tags": [...],
        ":ty": "…", ":rel": 7, ":pub": "2026-07-20", ":tk": [...],
        ":gpk": "CARD", ":gsk": "007#2026-07-20", ":now": "2026-07-20T12:00:00+00:00",
    },
)

# Dedup existence check — BatchGetItem via resource, projection to key only.
resp = resource.batch_get_item(
    RequestItems={
        "ai-radar-cards": {
            "Keys": [{"card_id": h} for h in chunk],  # <=100 keys per call
            "ProjectionExpression": "card_id",
        }
    }
)
present = {row["card_id"] for row in resp["Responses"]["ai-radar-cards"]}
# (UnprocessedKeys retried — see Behavior Guarantees)

# Phase 2 feed read (DOCUMENTED, NOT IMPLEMENTED HERE):
table.query(
    IndexName="feed-by-score",
    KeyConditionExpression=Key("gsi_pk").eq("CARD"),
    ScanIndexForward=False,   # descending: highest score, then latest date, first
    Limit=50,
)
```

> **`Decimal` note.** The resource API rejects `float` and returns `Decimal` for
> numbers. Phase 1 writes only `relevance` (an `int` → stored fine) and never reads
> numbers back into a `Card` (`dedup_filter` projects `card_id` only; `upsert` is
> write-only). The **reserved `embedding`** (list of float) is therefore *not*
> written in Phase 1 — Phase 3 must convert floats to `Decimal` when it populates
> it. No `Decimal`↔`float` conversion is required by any Phase 1 code path.

> **Reserved words.** `name` is reserved; our attributes avoid it. `title`, `url`,
> `type` are handled defensively via `ExpressionAttributeNames` placeholders (`#t`,
> `#u`, `#ty`) — `type` is a DynamoDB reserved word.

### AWS CDK v2 (Python — `aws_cdk.aws_dynamodb`)

`TableV2` (the current L2 construct) with on-demand billing and an inline GSI:

```python
from aws_cdk import RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb

table = dynamodb.TableV2(
    self, "CardTable",
    table_name="ai-radar-cards",
    partition_key=dynamodb.Attribute(
        name="card_id", type=dynamodb.AttributeType.STRING
    ),
    billing=dynamodb.Billing.on_demand(),
    removal_policy=RemovalPolicy.RETAIN,          # human decision: keep real data
    global_secondary_indexes=[
        dynamodb.GlobalSecondaryIndexPropsV2(
            index_name="feed-by-score",
            partition_key=dynamodb.Attribute(
                name="gsi_pk", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="gsi_sk", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )
    ],
)
```

## Key schema (LOCKED — changing any of this later is a data migration)

### Base table `ai-radar-cards`

| Role | Attribute | Type | Value |
|---|---|---|---|
| **PK** | `card_id` | S | `sha256(url).hexdigest()[:16]` — identical to `RawItem.url_hash` |

No base-table sort key (PK-only; each card is one item, point-addressable by hash).

### Global Secondary Index `feed-by-score` (designed now for Phase 2)

| Role | Attribute | Type | Value |
|---|---|---|---|
| **GSI PK** | `gsi_pk` | S | constant `"CARD"` (single partition — human decision, no bucketing) |
| **GSI SK** | `gsi_sk` | S | `f"{relevance:03d}#{published}"` (zero-padded score, then ISO date) |
| Projection | — | — | `ALL` (feed query returns whole cards, no second read) |

> **⚠️ Speculative-index flag.** `feed-by-score` is added now for a **Phase 2
> feed-read access pattern that has no consumer in this codebase yet.** This is a
> deliberate, documented exception to architecture-principles §"no speculative
> interfaces," justified because a DynamoDB key/index change after data exists is a
> migration, not a refactor (§"Boundaries" 4 — the table's key design *is* the infra
> seam). Phase 1 **writes** `gsi_pk`/`gsi_sk` on every card so the index is
> populated; Phase 1 **never reads** the GSI. The read query above is documented for
> validation only and is out of scope to implement.
>
> `gsi_sk` sorts correctly because `relevance` (1–10, zero-padded to 3 digits →
> `001`…`010`; width 3 tolerates a future 0–999 scale) sorts lexically = numerically,
> and ISO `published` (`YYYY-MM-DD`) sorts lexically = chronologically. A dateless
> card yields `"007#"`, which sorts *before* any dated card of the same score
> (undated ranks last within a score band under `ScanIndexForward=False`) —
> acceptable and documented.

### Item schema (one DynamoDB item per card)

| Attribute | Type | Source | Notes |
|---|---|---|---|
| `card_id` | S | `sha256(Card.url)[:16]` | PK |
| `title` | S | `Card.title` | |
| `url` | S | `Card.url` | |
| `source` | S | `Card.source` | |
| `summary` | S | `Card.summary` | |
| `tags` | L(S) | `Card.tags` | list of strings |
| `type` | S | `Card.type` | reserved word → placeholder in expressions |
| `relevance` | N | `Card.relevance` | int; also the score in `gsi_sk` |
| `published` | S | `Card.published` | ISO date or `""` |
| `takeaways` | L(S) | `Card.takeaways` | list of strings (may be empty) |
| `created_at` | S | write time | ISO8601 UTC; set once via `if_not_exists`, then stable |
| `updated_at` | S | write time | ISO8601 UTC; advances on every `upsert` |
| `gsi_pk` | S | constant `"CARD"` | GSI PK (written now, read in Phase 2) |
| `gsi_sk` | S | `f"{relevance:03d}#{published}"` | GSI SK (written now, read in Phase 2) |
| `embedding` | L(N) | **absent** | **RESERVED for Phase 3**; never written by Phase 1 code |

## Interfaces

### Config knobs (`src/curation/config.py` — MODIFY: append DynamoDB block)

Extend the existing Spec 02 module (do **not** create a new file, do **not** edit
`src/spike/config.py`). Same env-overridable module-level constant style.

```python
# --- DynamoDB card store (Spec 03) ---------------------------------------
# Base table name. The CDK construct provisions this exact name; the store reads
# it here so both sides agree without a CloudFormation-output lookup.
CARD_TABLE_NAME: str = os.getenv("CARD_TABLE_NAME", "ai-radar-cards")

# Feed-read GSI (designed now for Phase 2; written by Phase 1, read by Phase 2).
FEED_GSI_NAME: str = "feed-by-score"       # constant — matches the CDK construct
FEED_GSI_PARTITION: str = "CARD"           # single constant GSI partition (no bucketing)

# Store selector for the local entrypoint: "json" (default) | "dynamo".
CARD_STORE_BACKEND: str = os.getenv("CARD_STORE_BACKEND", "json")
```

> Region is **not** re-declared here — the store imports `AWS_REGION` from
> `spike.config` (already env-overridable, already `load_dotenv()`-backed).

### `DynamoCardStore` (`src/curation/dynamo.py` — CREATE)

Implements the Spec 01 `CardStore` Protocol. **Infra-edge adapter**: the only place
in `src/curation/` that imports `boto3` (same precedent as `spike/bedrock.py`). Lazy
singleton resource mirrors `spike.bedrock.bedrock_client()`.

```python
from __future__ import annotations

from spike.cards import Card
from spike.feeds import RawItem


class DynamoCardStore:
    """CardStore backed by a DynamoDB table (Spec 03).

    Implements the Spec 01 `CardStore` Protocol (dedup_filter + upsert).
    `boto3` is confined to this adapter — nodes/graph/state never import it,
    so the compiled graph stays portable onto AgentCore Runtime unchanged.
    """

    def __init__(self, table_name: str | None = None, client=None) -> None:
        """`table_name` defaults to `config.CARD_TABLE_NAME`. `client` is an
        optional boto3 DynamoDB **ServiceResource** (from
        `boto3.resource("dynamodb")`); when None a lazily-created, region-bound
        singleton resource is used. Tests inject a `moto`-backed resource."""
        ...

    def dedup_filter(self, items: list[RawItem]) -> list[RawItem]:
        """Return, order-preserving, only items whose `card_id` (== url_hash) is
        NOT already an item in the table. Existence is checked via BatchGetItem
        (chunks of <=100 keys, projecting `card_id` only). Never raises on an
        empty input (returns []). Idempotent: after upsert() of the resulting
        cards, a repeat call over the same items returns []."""
        ...

    def upsert(self, cards: list[Card]) -> None:
        """Insert-or-replace each card via `update_item` (per-card try/except so
        one bad card doesn't sink the batch). SETs every Card content field +
        gsi_pk/gsi_sk + updated_at (=now) + created_at (=if_not_exists(created_at,
        now)). NEVER writes `embedding`, so a Phase-3-populated vector survives a
        re-run. `card_id` derived from `Card.url` via the same sha256(url)[:16]
        rule as RawItem.url_hash. No-op on an empty list."""
        ...

    def failures(self) -> int:
        """Count of cards that raised during the last upsert() (0 if clean).
        Lets a caller/observer surface a partially-failed persist (Spec 06)."""
        ...
```

Behavior of `dedup_filter(items)`:
1. Empty input → return `[]` immediately (no AWS call).
2. Build the ordered list of `card_id`s (`item.url_hash`). Deduplicate the *query*
   keys (a batch may contain the same hash twice) but preserve the original item
   order for the return value.
3. For each chunk of ≤100 unique keys, `resource.batch_get_item` projecting
   `card_id`; union the returned `card_id`s into a `present` set. Retry
   `UnprocessedKeys` until empty (bounded retries).
4. Return `[item for item in items if item.url_hash not in present]` — original
   order preserved.

Behavior of `upsert(cards)`:
1. Empty list → return immediately (no AWS call).
2. `now = datetime.now(timezone.utc).isoformat()` computed once per call.
3. For each card, in a `try/except Exception` (log `! failed to persist <url>: …`,
   `failures += 1`, `continue`): compute `card_id = sha256(card.url)[:16]`, build
   the `UpdateExpression` per the pinned surface, and call `table.update_item`.
   `gsi_sk = f"{card.relevance:03d}#{card.published}"`, `gsi_pk = "CARD"`.
4. Return `None`. The `embedding` attribute is never referenced.

> A batch writer (`table.batch_writer()`) is **not** used, because `batch_writer`
> issues `PutItem` (full-item replace) which would (a) reset `created_at` and (b)
> erase a reserved/populated `embedding`. Per-item `update_item` is the deliberate
> choice that satisfies the idempotency + reserved-embedding guarantees. At ~80
> cards/day the extra request count is immaterial (§7).

### CDK construct (`infra/lib/card_store.py` — CREATE)

> Directory is `infra/lib/`, **not** `infra/constructs/` — a local `constructs`
> package on `sys.path` would shadow the CDK `constructs` library
> (`from constructs import Construct`). `lib/` avoids that collision.

Reusable L3 construct wrapping the `TableV2` + GSI. Not inline in the stack, so
Specs 04–05 can compose it.

```python
from __future__ import annotations

from aws_cdk import RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from constructs import Construct


class CardStoreTable(Construct):
    """Provisions the AI Radar card table (on-demand) + feed-read GSI.

    Exposes `.table` (the dynamodb.TableV2) for grants/outputs by callers.
    Key schema matches specs/dynamodb-card-store/contract.md exactly — a change
    here is a data migration.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        table_name: str = "ai-radar-cards",
    ) -> None:
        super().__init__(scope, construct_id)
        self.table = dynamodb.TableV2(
            self, "Table",
            table_name=table_name,
            partition_key=dynamodb.Attribute(
                name="card_id", type=dynamodb.AttributeType.STRING
            ),
            billing=dynamodb.Billing.on_demand(),
            removal_policy=RemovalPolicy.RETAIN,
            global_secondary_indexes=[
                dynamodb.GlobalSecondaryIndexPropsV2(
                    index_name="feed-by-score",
                    partition_key=dynamodb.Attribute(
                        name="gsi_pk", type=dynamodb.AttributeType.STRING
                    ),
                    sort_key=dynamodb.Attribute(
                        name="gsi_sk", type=dynamodb.AttributeType.STRING
                    ),
                    projection_type=dynamodb.ProjectionType.ALL,
                )
            ],
        )
```

### CDK stack + app (`infra/stacks/card_store_stack.py`, `infra/app.py` — CREATE)

```python
# infra/stacks/card_store_stack.py
from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from lib.card_store import CardStoreTable  # infra/ on sys.path via app.py


class CardStoreStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        store = CardStoreTable(self, "CardStore", table_name="ai-radar-cards")
        CfnOutput(self, "CardTableName", value=store.table.table_name)
        CfnOutput(self, "FeedGsiName", value="feed-by-score")
```

```python
# infra/app.py
#!/usr/bin/env python3
from __future__ import annotations

import aws_cdk as cdk

from stacks.card_store_stack import CardStoreStack

app = cdk.App()
CardStoreStack(app, "AiRadarCardStore")   # env resolved from CDK context / profile
app.synth()
```

> The exact intra-`infra/` import wiring (`sys.path`, package vs. flat modules) is
> finalized in the roadmap; `cdk.json` sets `"app": "uv run python infra/app.py"`.
> **`cdk deploy` is out of scope** — the deliverable is a `cdk synth`-able app.

### Local entrypoint (`run_curation.py` — MODIFY)

Add store selection mirroring Spec 02's discoverer auto-select. When
`config.CARD_STORE_BACKEND == "dynamo"`, build `DynamoCardStore()`; else keep
`JsonFileCardStore(...)`. No graph edits — the store is injected into the unchanged
`build_graph(store, discoverer)`.

## State Changes

None to the graph. `DynamoCardStore` is a drop-in `CardStore` passed to the
**unchanged** `build_graph(store, discoverer)`. `CurationState`, nodes, edges, and
`interfaces.py` are untouched — the seam holds. The only new persistent state is the
DynamoDB table itself (provisioned by the CDK construct), which replaces
`.spike_cache/{seen,cards}.json` when the Dynamo backend is selected.

## Behavior Guarantees

1. `DynamoCardStore` structurally satisfies the Spec 01 `CardStore` Protocol:
   `isinstance(DynamoCardStore(...), CardStore)` is `True` (`runtime_checkable`),
   and `build_graph(DynamoCardStore(...), discoverer)` compiles and invokes with
   **no** edit to `graph.py`/`nodes.py`/`state.py`/`interfaces.py`.
2. `card_id == sha256(url.encode()).hexdigest()[:16]` for both a `RawItem`
   (`item.url_hash`) and its resulting `Card` (`sha256(Card.url)[:16]`), so
   `dedup_filter` after `upsert` of a batch excludes exactly those items
   (idempotency bridge — same rule as `RawItem.url_hash`, `local._url_hash`, and
   Spec 01 Guarantee 8).
3. `dedup_filter(items)` returns the input items whose `card_id` is absent from the
   table, **in original order**, and returns `[]` for empty input without any AWS
   call.
4. **Upsert idempotency (testable):** calling `upsert(batch)` twice yields exactly
   `len({card_id})` items (one per distinct `card_id`) — no duplicates; each item's
   `created_at` is unchanged between the two runs; each item's `updated_at` is `>=`
   (advances to the second run's timestamp). Verified against `moto`.
5. `upsert` **never writes** the `embedding` attribute; an item pre-seeded with an
   `embedding` retains it byte-for-byte after a re-`upsert` (reserved-shape /
   no-clobber guarantee for Phase 3).
6. Every upserted item carries `gsi_pk="CARD"` and `gsi_sk=f"{relevance:03d}#{published}"`,
   so the `feed-by-score` GSI is populated and a Phase 2
   `query(IndexName="feed-by-score", KeyConditionExpression=Key("gsi_pk").eq("CARD"),
   ScanIndexForward=False)` returns cards ordered by descending score then date with
   no scan. (Written now; the query is documented, not implemented.)
7. `upsert` is per-card resilient: one card raising during its `update_item`
   increments `failures()`, is skipped, and the remaining cards still persist (run
   completes) — mirrors Spec 01's per-item try/except.
8. `boto3` is imported **only** in `src/curation/dynamo.py` (an infra adapter);
   it does not appear in `nodes.py`/`graph.py`/`state.py`/`interfaces.py`/`local.py`.
   Portability of the compiled graph is preserved.
9. The CDK construct provisions the table in **on-demand** billing with
   `removal_policy=RETAIN` and the `feed-by-score` GSI (projection `ALL`); the
   synthesized template's key schema matches this contract exactly.
10. All store tests run against `moto` (`mock_aws`) with **zero** real-AWS calls;
    no test constructs a real (non-mocked) DynamoDB client that reaches AWS.

## Error Handling Contract

| Error Condition | Behavior | User Impact |
|---|---|---|
| One card's `update_item` raises (throttle, malformed value) | per-card `try/except` in `upsert`: log `! failed to persist <url>`, `failures += 1`, skip, continue | That card omitted from the store; run completes; counter reflects it |
| `dedup_filter` / `upsert` called with `[]` | return immediately (`[]` / `None`), no AWS call | No-op; no cost |
| `batch_get_item` returns `UnprocessedKeys` (throttle/partial) | retry the unprocessed keys (bounded); union all responses before filtering | Correct dedup result; slightly slower under throttle |
| A card's `card_id` appears twice in one `upsert` batch | last `update_item` wins (same PK); one item persisted, `updated_at` = last write | One row per URL (expected); no duplicate |
| Same `RawItem` seen across runs (already stored) | `dedup_filter` excludes it (its `card_id` is present) | Not re-summarized, not re-persisted (idempotent daily re-run) |
| Table missing / wrong name / no AWS creds (real backend only) | boto3 raises (`ResourceNotFoundException` / credential error) out of the store — persistence is not best-effort at the connection level | Run errors loudly (mis-provisioned infra surfaced, not silently lost) |
| Reserved word collision (`type`) in an expression | avoided via `ExpressionAttributeNames` placeholders (`#ty` etc.) | N/A (handled) |

## Dependencies

- **Internal (imported, not forked):**
  - `spike.feeds.RawItem` (and its `url_hash`), `spike.cards.Card`
  - `spike.config.AWS_REGION`
  - `curation.interfaces.CardStore` (the stable Protocol — imported for typing /
    conformance, **not** modified)
  - `curation.config` (extended with the DynamoDB block above)
- **External (new):**
  - `moto` (dev group) — in-process DynamoDB mock; add via `uv add --group dev moto`.
    Pin the resolved version in `uv.lock`. Tests use `moto.mock_aws`.
  - `aws-cdk-lib`, `constructs` (infra group) — add via
    `uv add --group infra aws-cdk-lib constructs`. `aws-cdk-lib` must be a version
    providing `TableV2` / `Billing.on_demand()` (≥ 2.133; let `uv` resolve latest 2.x
    and pin in `uv.lock`). API surface verified via Context7 2026-07-20.
- **External (existing):** `boto3` (already in `pyproject.toml`; used only inside
  `dynamo.py`), `langgraph`/`feedparser`/`rich`/`python-dotenv` (unchanged).

## Integration Points

- **Spec 01 (`curation-graph`)** — `DynamoCardStore` is consumed via the unchanged
  `build_graph(store, discoverer)` and the unchanged `CardStore` Protocol seam. The
  `dedup_filter`/`upsert` semantics defined by Spec 01 are the contract this store
  satisfies. No graph/node/state/interface edits.
- **Spec 02 (`tavily-discovery`)** — the composite/store dedup layers agree because
  both key on the same `sha256(url)[:16]` rule: the composite trims intra-run
  cross-source dups; this store trims already-curated items across runs. This spec
  **appends** to the `src/curation/config.py` Spec 02 created (no fork).
- **Spec 04/05 (`runtime-packaging` / scheduling)** — import `CardStoreTable` to
  compose the deployed stack, grant the Runtime's role read/write on the table, set
  `CARD_TABLE_NAME`/`CARD_STORE_BACKEND=dynamo` in the Runtime env, and run
  `cdk deploy`. This spec delivers the `cdk synth`-able construct/app; it does not
  deploy or wire IAM grants.
- **Spec 06 (`run-observability`)** — `DynamoCardStore.failures()` exposes
  partially-failed persists for the run summary (parallel to the discoverer
  `failures()` in Spec 02).
- **Phase 2 (feed-read API)** — consumes the `feed-by-score` GSI via the documented
  `query`. The GSI keys are written now so Phase 2 needs no backfill.
- **Phase 3 (brute-force RAG)** — populates the reserved inline `embedding` (list of
  `Decimal`); `upsert`'s no-clobber guarantee (5) means re-curation won't erase it.

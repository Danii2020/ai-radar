# Roadmap: dynamodb-card-store

## Implementation Phases

### Phase 1: Foundation — dependencies, config knobs, CDK skeleton
**Goal**: Add the dev/infra dependencies and the config seam, and stand up an
empty-but-`synth`-able CDK app. No store logic yet.
**Dependencies**: None (Specs 01–02 already merged)
**Estimated complexity**: Low

(ensure the env is current: `uv sync`)

1. `uv add --group dev moto` — updates `pyproject.toml` + `uv.lock`. Confirm
   `uv run python -c "import moto; from moto import mock_aws"` works.
2. `uv add --group infra aws-cdk-lib constructs` — updates `pyproject.toml` +
   `uv.lock`. Confirm `uv run python -c "import aws_cdk; from aws_cdk import aws_dynamodb"`
   works and that `aws_dynamodb.TableV2` / `aws_dynamodb.Billing.on_demand` resolve
   (TableV2 requires aws-cdk-lib ≥ 2.133; `uv` pins the resolved 2.x in `uv.lock`).
3. ~~Verify CDK `TableV2`/`Billing.on_demand()`/GSI props + boto3 `update_item`/
   `batch_get_item`/`query` signatures via Context7.~~ **Done (2026-07-20;
   `/websites/aws_amazon_cdk_api_v2_python`, `/boto/boto3`)** — pinned in
   contract.md "AWS / library API surface". No rework expected.
4. Append the DynamoDB block to `src/curation/config.py` (`CARD_TABLE_NAME`,
   `FEED_GSI_NAME`, `FEED_GSI_PARTITION`, `CARD_STORE_BACKEND`) exactly as in
   contract.md. Do **not** create a new module and do **not** edit
   `src/spike/config.py`.
5. Create the `infra/` skeleton: `infra/app.py`, `infra/stacks/card_store_stack.py`,
   `infra/lib/card_store.py` (NOT `infra/constructs/` — that would shadow the CDK
   `constructs` package on `sys.path`), `infra/cdk.json` (`"app": "uv run python
   infra/app.py"`), and finalize the intra-`infra/` import path (add `infra/` to
   `sys.path` in `app.py`, or ship `__init__.py` package files — pick one, document
   it in tasks.md). Confirm `uv run cdk synth` (or `uv run python infra/app.py`)
   runs once the construct lands in Phase 2.

### Phase 2: Core Logic — CDK construct + DynamoCardStore
**Goal**: Implement the reusable table construct and the store adapter.
**Dependencies**: Phase 1
**Estimated complexity**: Medium

1. `infra/lib/card_store.py`: implement `CardStoreTable(Construct)` exactly
   per contract.md — `TableV2`, PK `card_id` (S), `Billing.on_demand()`,
   `removal_policy=RETAIN`, one GSI `feed-by-score` (PK `gsi_pk` S, SK
   `gsi_sk` S, projection `ALL`). Expose `.table`.
2. `infra/stacks/card_store_stack.py`: `CardStoreStack` instantiates the construct
   with `table_name="ai-radar-cards"` and emits `CfnOutput`s (`CardTableName`,
   `FeedGsiName`). `infra/app.py`: `cdk.App()` → `CardStoreStack` → `app.synth()`.
   Confirm `uv run cdk synth` produces a template with the table + GSI.
3. `src/curation/dynamo.py`: implement `DynamoCardStore`:
   - `__init__(table_name=None, client=None)` — default `table_name` to
     `config.CARD_TABLE_NAME`; lazy singleton `boto3.resource("dynamodb",
     region_name=spike.config.AWS_REGION)` when `client` is None; `self._table =
     resource.Table(table_name)`. This is the **only** `boto3` import in
     `src/curation/`.
   - `dedup_filter(items)`: empty → `[]`; unique `card_id` query keys (preserve item
     order for the result); `batch_get_item` in ≤100-key chunks projecting `card_id`;
     retry `UnprocessedKeys`; return items whose `url_hash` not in the `present` set.
   - `upsert(cards)`: empty → return; compute `now` once; per-card `try/except`
     (log + `failures += 1` + continue); `card_id = sha256(card.url)[:16]`;
     `update_item` SETting all content fields + `gsi_pk="CARD"` +
     `gsi_sk=f"{card.relevance:03d}#{card.published}"` + `updated_at=now` +
     `created_at=if_not_exists(created_at, now)`; **never** reference `embedding`;
     use `ExpressionAttributeNames` for `type`/`title`/`url`.
   - `failures()` accessor.

### Phase 3: Integration — entrypoint store selection
**Goal**: Let the local entrypoint drive the *unchanged* graph against DynamoDB.
**Dependencies**: Phase 2
**Estimated complexity**: Low

1. `run_curation.py` (MODIFY): select the store from `config.CARD_STORE_BACKEND` —
   `"dynamo"` → `DynamoCardStore()`, else the existing `JsonFileCardStore(...)`.
   Pass the chosen store to the unchanged `build_graph(store, discoverer)`; render
   cards + counters (incl. `store.failures()` when the Dynamo backend is active).
   No graph/node edits.
2. Manual smoke (human, deferred): with a real deployed table + AWS creds and
   `CARD_STORE_BACKEND=dynamo`, `uv run run_curation.py` and confirm items persist,
   a re-run dedups (zero new cards), and the GSI is populated. Not run in this spec
   (no `cdk deploy` here).

### Phase 4: Testing & Validation
**Goal**: Prove every guarantee against `moto` — zero real-AWS calls.
**Dependencies**: Phase 3
**Estimated complexity**: Medium

1. `tests/conftest.py` (MODIFY, additive): add a `moto`-backed fixture — a
   `mock_aws` DynamoDB resource plus a helper that creates the `ai-radar-cards`
   table with the exact contract key schema (PK `card_id`; GSI `feed-by-score`
   PK `gsi_pk`/SK `gsi_sk`, projection ALL; on-demand). Do not modify existing
   Spec 01/02 fixtures.
2. `tests/test_dynamo_store.py` (CREATE): store behavior against `moto`:
   - `upsert` then `dedup_filter` excludes persisted items; `card_id` derived from
     `Card.url` matches `RawItem.url_hash` (T1, Guarantee 2);
   - `dedup_filter` order-preserving, returns only unseen, `[]` on empty (T2, G3);
   - idempotency: upsert same batch twice → one item per `card_id`, `created_at`
     stable, `updated_at` advances, no duplicates (T3, G4);
   - item schema: all `Card` fields + `card_id`/`created_at`/`updated_at`/`gsi_pk`/
     `gsi_sk` written; `embedding` absent (T4);
   - `gsi_sk == f"{relevance:03d}#{published}"`; dateless card → trailing `#` (T5, G6);
   - no-clobber: pre-seed an item with an `embedding`, re-`upsert`, embedding
     survives (T6, G5);
   - resilience: one card raising in `update_item` → `failures()==1`, others persist
     (T7, G7).
3. `tests/test_dynamo_store.py` (Protocol + seam): `isinstance(store, CardStore)` is
   True; `build_graph(DynamoCardStore(moto_table), FakeDiscoverer)` with stubbed
   `bedrock.summarize` invokes end-to-end and persists cards — proving the Spec 01
   graph is unchanged (T8, G1).
4. GSI read-shape validation (T9, G6): against `moto`, after upserting cards with
   varied relevance/date, `query(IndexName="feed-by-score",
   KeyConditionExpression=Key("gsi_pk").eq("CARD"), ScanIndexForward=False)` returns
   them ordered by descending score then date. (Validates the index design; the
   production reader is Phase 2 and stays unimplemented.)
5. Portability test (T10, G8): assert `boto3` is imported by `dynamo.py` only and by
   none of `nodes.py`/`graph.py`/`state.py`/`interfaces.py`/`local.py` (AST/grep).
6. `tests/test_infra.py` (CREATE, T11, G9): `cdk.assertions.Template.from_stack`
   over `CardStoreStack` asserts a `AWS::DynamoDB::GlobalTable`/`Table` with
   `BillingMode=PAY_PER_REQUEST`, key schema `card_id`, a `feed-by-score` GSI on
   `gsi_pk`/`gsi_sk` with projection `ALL`, and `DeletionPolicy: Retain`. No AWS
   calls (synth-only).
7. `uv run pytest`; all green (Spec 01/02 suite unchanged + new). Update `audit.md`
   statuses.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `put_item`/`batch_writer` used and it clobbers `created_at` / a Phase 3 `embedding` | ~~Med~~ **Designed out** | High | Contract mandates `update_item` with `if_not_exists(created_at)` and never SETting `embedding`; Guarantee 5 + no-clobber test |
| Key schema chosen wrong → migration after data exists | Low | High | Schema LOCKED in contract.md; `test_infra.py` asserts synthesized keys; human decisions (RETAIN, constant GSI PK) baked in |
| `moto` DynamoDB behavior diverges from real (GSI ordering, `update_item` semantics) | Low | Med | Use `moto.mock_aws`; keep assertions to documented DynamoDB semantics (string-sorted SK); flag any moto quirk in audit |
| `boto3` leaks into node/graph code (breaks portability) | Low | High | Guarantee 8 + portability test asserting `boto3` only in `dynamo.py` |
| Single constant GSI partition hot-spots at scale | Low | Med | Human-accepted for Phase 1/2 volumes (~80/day); monthly-bucketing escape hatch documented (not built) |
| `TableV2` unavailable in the resolved `aws-cdk-lib` | Low | Med | Phase 1 step 2 verifies import; require ≥2.133; `uv.lock` pins the resolved version |
| `Decimal`/`float` mismatch when Phase 3 adds `embedding` | Low (Phase 3) | Low | Contract notes floats→`Decimal` is Phase 3's job; Phase 1 writes no floats |
| Reserved-word (`type`) expression error | Low | Low | `ExpressionAttributeNames` placeholders per contract; covered by upsert tests |
| Real-AWS call leaks into the test suite | Low | Med | All store tests wrapped in `mock_aws`; infra tests are synth-only; no live client constructed |
| CDK app import path fragile (`infra/` not on path) | Med | Low | Phase 1 step 5 fixes the import strategy once; `cdk.json` uses `uv run python infra/app.py` |

## File Change Map

- `pyproject.toml` — MODIFY — add `moto` (dev group), `aws-cdk-lib`+`constructs` (infra group) via `uv add`.
- `uv.lock` — MODIFY — regenerated by `uv add` (source of truth for versions).
- `src/curation/config.py` — MODIFY — append the DynamoDB block (`CARD_TABLE_NAME`, `FEED_GSI_NAME`, `FEED_GSI_PARTITION`, `CARD_STORE_BACKEND`).
- `src/curation/dynamo.py` — CREATE — `DynamoCardStore` (only `boto3` import site in `src/curation/`).
- `run_curation.py` — MODIFY — select `DynamoCardStore` vs `JsonFileCardStore` from `CARD_STORE_BACKEND`.
- `infra/app.py` — CREATE — CDK `App` entrypoint (`cdk synth`-able).
- `infra/stacks/card_store_stack.py` — CREATE — `CardStoreStack` + `CfnOutput`s.
- `infra/lib/card_store.py` — CREATE — reusable `CardStoreTable` construct (`lib/`, not `constructs/`, to avoid shadowing the CDK `constructs` package).
- `infra/cdk.json` — CREATE — `"app": "uv run python infra/app.py"`.
- `infra/__init__.py`, `infra/stacks/__init__.py`, `infra/lib/__init__.py` — CREATE (if the package-import strategy is chosen) — see Phase 1 step 5.
- `tests/conftest.py` — MODIFY (additive) — `moto` DynamoDB fixture + table-creation helper; existing fixtures untouched.
- `tests/test_dynamo_store.py` — CREATE — store behavior, idempotency, no-clobber, seam, GSI read-shape, portability tests.
- `tests/test_infra.py` — CREATE — CDK `Template` assertions (synth-only).
- `.env.example` — MODIFY/CREATE — document `CARD_TABLE_NAME=` / `CARD_STORE_BACKEND=` (no secrets).
- `src/curation/interfaces.py` — UNCHANGED — stable `CardStore` seam.
- `src/curation/{graph,nodes,state,local}.py` — UNCHANGED — Specs 01/02 code.
- `src/spike/**` — UNCHANGED — reference plane, do not edit.

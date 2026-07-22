# Tasks: dynamodb-card-store

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

## Phase 1: Foundation — dependencies, config knobs, CDK skeleton
- [x] Task 1.1: `uv add --group dev moto`; verify `uv run python -c "from moto import mock_aws"` — `pyproject.toml`, `uv.lock` — done pre-session; verified working in this session (`uv sync --group dev --group infra`)
- [x] Task 1.2: `uv add --group infra aws-cdk-lib constructs`; verify `uv run python -c "from aws_cdk import aws_dynamodb; aws_dynamodb.TableV2; aws_dynamodb.Billing.on_demand"` (require aws-cdk-lib ≥ 2.133) — `pyproject.toml`, `uv.lock` — done pre-session (aws-cdk-lib 2.261.0); verified in this session
- [x] Task 1.3: Verify CDK `TableV2`/`Billing.on_demand()`/GSI props + boto3 `update_item`(`if_not_exists`)/`batch_get_item`/`query` via Context7 — **done 2026-07-20 (`/websites/aws_amazon_cdk_api_v2_python`, `/boto/boto3`); pinned in contract.md "AWS / library API surface"** (no file)
- [x] Task 1.4: Append the DynamoDB block (`CARD_TABLE_NAME`, `FEED_GSI_NAME`, `FEED_GSI_PARTITION`, `CARD_STORE_BACKEND`) per contract — `src/curation/config.py` — do NOT edit `src/spike/config.py`
- [x] Task 1.5: Create the `infra/` skeleton + `cdk.json` (`"app": "uv run python infra/app.py"`); decide + document the intra-`infra/` import strategy (sys.path insert in `app.py` **or** `__init__.py` packages); use `infra/lib/` NOT `infra/constructs/` (shadows the CDK `constructs` package) — `infra/app.py`, `infra/cdk.json`, `infra/stacks/`, `infra/lib/` — import strategy: `infra/app.py` inserts `infra/` onto `sys.path` (mirrors `tests/test_infra.py`'s own insert); `__init__.py` files also added under `infra/`, `infra/lib/`, `infra/stacks/` for clean package resolution either way
- [x] Task 1.6: Document `CARD_TABLE_NAME=` / `CARD_STORE_BACKEND=` in `.env.example` (no secrets); confirm `.env` gitignored — `.env.example`

## Phase 2: Core Logic — CDK construct + DynamoCardStore
- [x] Task 2.1: Implement `CardStoreTable(Construct)` — `TableV2`, PK `card_id`(S), `Billing.on_demand()`, `removal_policy=RETAIN`, GSI `feed-by-score` (PK `gsi_pk`(S), SK `gsi_sk`(S), projection ALL); expose `.table` — `infra/lib/card_store.py`
- [x] Task 2.2: Implement `CardStoreStack` (instantiate construct, `CfnOutput` `CardTableName`/`FeedGsiName`) + `app.py` (`App`→stack→`synth`); confirm `uv run cdk synth` emits table + GSI — `infra/stacks/card_store_stack.py`, `infra/app.py` — verified via direct `app.synth()` sanity script (see verification loop); no `uv run cdk` CLI available/needed since `test_infra.py` synths in-process
- [x] Task 2.3: Implement `DynamoCardStore.__init__(table_name=None, client=None)` — default `table_name=config.CARD_TABLE_NAME`; lazy singleton `boto3.resource("dynamodb", region_name=spike.config.AWS_REGION)`; `self._table = resource.Table(name)`; ONLY `boto3` import in `src/curation/` — `src/curation/dynamo.py`
- [x] Task 2.4: Implement `DynamoCardStore.dedup_filter(items)` — empty→`[]`; unique `card_id` query keys, preserve item order for result; `batch_get_item` ≤100-key chunks projecting `card_id`; retry `UnprocessedKeys`; return items whose `url_hash` not present — `src/curation/dynamo.py`
- [x] Task 2.5: Implement `DynamoCardStore.upsert(cards)` — empty→return; `now` once; per-card `try/except` (log + `failures += 1` + continue); `card_id=sha256(card.url)[:16]`; `update_item` SET all Card fields + `gsi_pk="CARD"` + `gsi_sk=f"{card.relevance:03d}#{card.published}"` + `updated_at=now` + `created_at=if_not_exists(created_at, now)`; NEVER write `embedding`; `ExpressionAttributeNames` for `type`/`title`/`url` — `src/curation/dynamo.py` — **deviation**: also added a placeholder for `source` (`#src`), which real DynamoDB (and `moto`) reject as a reserved word even though the contract's pinned example left it unescaped; required for `test_upsert_writes_full_item_schema_and_never_writes_embedding` et al. to pass against `moto`. No test assertion depends on the literal expression string, only on the persisted attribute values, so this doesn't touch any locked contract behavior — flagged here per SDD process rather than silently deviating.
- [x] Task 2.6: Implement `DynamoCardStore.failures()` accessor — `src/curation/dynamo.py`

## Phase 3: Integration — entrypoint store selection
- [x] Task 3.1: Select store from `config.CARD_STORE_BACKEND` (`"dynamo"`→`DynamoCardStore()`, else `JsonFileCardStore(...)`); pass to the unchanged `build_graph(store, discoverer)`; render cards + counters (incl. `store.failures()` for the Dynamo backend); no graph/node edits — `run_curation.py`
- [!] Task 3.2: Manual smoke against a real deployed table (`CARD_STORE_BACKEND=dynamo`, real creds): `uv run run_curation.py`, confirm persist + idempotent re-run + populated GSI — deferred to the human; this spec does no `cdk deploy`

## Phase 4: Testing & Validation
- [x] Task 4.1: Add a `moto`-backed DynamoDB fixture + table-creation helper (exact contract key schema: PK `card_id`; GSI `feed-by-score` `gsi_pk`/`gsi_sk`, projection ALL; on-demand) — additive, do not touch existing Spec 01/02 fixtures — `tests/conftest.py` — pre-existing from the red-phase test-writer; not modified in this session
- [x] Task 4.2: Store tests T1–T3 (dedup/`card_id` bridge; order-preserving + empty; idempotency: 2× batch → one item/card_id, `created_at` stable, `updated_at` advances) — `tests/test_dynamo_store.py` — all passing, unmodified
- [x] Task 4.3: Schema + GSI-key tests T4–T5 (all fields + card_id/created_at/updated_at/gsi_pk/gsi_sk written, `embedding` absent, `type` handled; `gsi_sk` format incl. dateless trailing `#`) — `tests/test_dynamo_store.py` — all passing, unmodified
- [x] Task 4.4: No-clobber + resilience tests T6–T7 (pre-seeded `embedding` survives re-upsert; one card raising → `failures()==1`, others persist) — `tests/test_dynamo_store.py` — all passing, unmodified
- [x] Task 4.5: Protocol + seam test T8 (`isinstance(store, CardStore)`; `build_graph(DynamoCardStore(moto_table), FakeDiscoverer)` with stubbed `bedrock.summarize` invokes end-to-end → cards persisted) — `tests/test_dynamo_store.py` — all passing, unmodified
- [x] Task 4.6: GSI read-shape test T9 (`query(feed-by-score, gsi_pk=CARD, ScanIndexForward=False)` returns score-desc/date-desc) — validates the Phase 2 index design; do NOT implement a production reader — `tests/test_dynamo_store.py` — passing, unmodified; no production reader added
- [x] Task 4.7: Portability test T10 (`boto3` imported only in `dynamo.py`; absent from nodes/graph/state/interfaces/local) — `tests/test_dynamo_store.py` — passing, unmodified
- [x] Task 4.8: CDK `Template` test T11 (synth-only: PAY_PER_REQUEST, `card_id` PK, `feed-by-score` GSI gsi_pk/gsi_sk projection ALL, DeletionPolicy Retain) — `tests/test_infra.py` — passing, unmodified
- [x] Task 4.9: Run `uv run pytest`; all green (Spec 01/02 suite unchanged + new T1–T12); leave `audit.md` status updates for the auditor to confirm independently — full suite: 43 passed (27 pre-existing Spec 01/02 + 16 new Spec 03)

## Blocked Items
- Task 3.2 — live smoke against a real deployed DynamoDB table; blocked on a human `cdk deploy` + AWS creds (out of scope for this spec, which delivers a `cdk synth`-able app only).

## Notes
- **Do not modify the stable seam:** `src/curation/interfaces.py` is unchanged; the
  `CardStore` Protocol shape is fixed. New runtime code lives in `src/curation/dynamo.py`
  + the appended `src/curation/config.py` block. Do not edit
  `graph.py`/`nodes.py`/`state.py`/`local.py` or `src/spike/**`.
- **Reuse, don't fork:** import `RawItem` (+ `url_hash`), `Card` from `spike`,
  `AWS_REGION` from `spike.config`, `CardStore` from `curation.interfaces`. Append to
  `curation.config` (created by Spec 02) — do not create a second config module.
- **`card_id` rule:** `sha256(url.encode()).hexdigest()[:16]` — identical across
  `RawItem.url_hash`, `local._url_hash`, and this store, so all dedup layers agree.
- **`update_item`, not `put_item`/`batch_writer`:** the deliberate choice that keeps
  `created_at` stable, advances `updated_at`, and NEVER clobbers the reserved
  Phase 3 `embedding`. Never reference `embedding` in any Phase 1 write.
- **Portability keystone:** `boto3` is imported ONLY in `dynamo.py` (infra adapter,
  same precedent as `spike/bedrock.py`); it must not appear in
  `nodes.py`/`graph.py`/`state.py`/`interfaces.py`/`local.py`.
- **Speculative-index flag:** `feed-by-score` is designed + written now for a Phase 2
  reader that does not exist yet — justified because a DynamoDB key/index change after
  data exists is a migration. Phase 1 writes the GSI keys and validates ordering via a
  `moto` query; it never ships a production GSI reader.
- **Human decisions (fixed):** `removal_policy=RETAIN`; single constant GSI partition
  `gsi_pk="CARD"` (no bucketing); `infra/` as a uv dependency-group in the root
  `pyproject.toml` (one lockfile/venv, not a nested project); table name
  `ai-radar-cards` (author's choice, env-overridable). **Point-in-time recovery
  (PITR) was considered and explicitly declined for Phase 1** to keep costs minimal;
  it is not part of the locked key schema and can be enabled later without a
  migration.
- **Testing convention (carried from Specs 01/02):** zero real-AWS calls in pytest —
  DynamoDB mocked in-process via `moto.mock_aws`; CDK tests are synth-only
  (`Template.from_stack`). No DynamoDB Local / Docker.
- **Cost discipline (§7):** on-demand billing; one GSI; brute-force cosine over this
  table later (no OpenSearch/KB vector backing). Dedup-before-summarize (Spec 01)
  preserved so Haiku never re-summarizes a stored item.
- **Out of scope (other specs/phases):** `cdk deploy`, IAM grants, Runtime/EventBridge
  wiring (Specs 04–05); the feed-read API/Lambda (Phase 2); embedding computation /
  vector search (Phase 3); any dedicated vector store.

## Proposed defaults needing human confirmation
All resolved with the human (see intent.md "Decisions"): RETAIN removal policy,
single constant GSI partition, `infra` uv dependency-group, table name
`ai-radar-cards`, and no PITR in Phase 1. No open questions remain.

## Implementation complete — 2026-07-21
All Phase 1-4 tasks done ([x]) except Task 3.2 ([!] blocked, out of scope per
spec). Full suite: `uv run pytest` → 43 passed, 0 failed (27 pre-existing
Spec 01/02 + 16 new Spec 03: 14 in `tests/test_dynamo_store.py`, 2 in
`tests/test_infra.py`). No red-phase test was modified.

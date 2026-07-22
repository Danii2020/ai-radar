# Audit: dynamodb-card-store

> AUDITED 2026-07-21 by sdd-auditor (green/implementation stage). Every row
> traces to `intent.md` (requirements) or `contract.md` (guarantees). All checks
> re-run independently (full suite, grep, git diff, ad-hoc `cdk synth`, empirical
> reserved-word probe) — not inferred from prior-agent reports.

## Requirements Checklist
| ID | Requirement | Source | Status | Notes |
|---|---|---|---|---|
| R1 | `DynamoCardStore` implements the Spec 01 `CardStore` Protocol (`dedup_filter` + `upsert`) exactly | intent.md Goal 1 | PASS | `isinstance(store, CardStore)` True (T8); signatures + docstrings match `interfaces.py`; extra `failures()` accessor is contract-sanctioned (Spec 06 hook) |
| R2 | Base-table PK `card_id = sha256(url)[:16]`, byte-identical to `RawItem.url_hash` / `local._url_hash`; key schema locked | intent.md Goal 2 | PASS | `_card_id` = `hashlib.sha256(url.encode()).hexdigest()[:16]`; T1 asserts the bridge; dedup layers agree |
| R3 | Feed-read GSI designed + written now for Phase 2 (constant `gsi_pk="CARD"`, `gsi_sk=score#date`, projection ALL); GSI keys written on every card | intent.md Goal 3 | PASS | `upsert` writes `gsi_pk`/`gsi_sk` on every item (T4, T5); read query documented only, not implemented (grep: no production GSI reader) |
| R4 | Inline `embedding` reserved in schema, never written by Phase 1, never clobbered on re-run | intent.md Goal 4 | PASS | `embedding` never referenced in any write path; no-clobber survival proven (T6) |
| R5 | Table provisioned by a reusable CDK construct, on-demand billing, `removal_policy=RETAIN` | intent.md Goal 5 | PASS | `CardStoreTable` construct; synth → `PAY_PER_REQUEST` + `DeletionPolicy: Retain` (T11 + ad-hoc synth) |
| R6 | Unchanged Spec 01 graph runs end-to-end against the Dynamo store (drop-in swap) | intent.md Goal 6 | PASS | T8 invokes `build_graph(DynamoCardStore, FakeDiscoverer)`; `git diff HEAD` on graph/nodes/state/interfaces/local empty |
| R7 | All tests pass against `moto` with zero real-AWS calls | intent.md Goal 7 | PASS | 43 passed; store tests wrapped in `mock_aws`; infra tests synth-only |
| R8 | Reuse-not-fork: `RawItem`/`Card`/`AWS_REGION`/`CardStore` imported; config appended not forked; `src/spike/**` + `interfaces.py` untouched | intent.md Constraints | PASS | Imports confirmed in `dynamo.py`; config block appended to `curation/config.py`; seam diff empty |
| R9 | Deps added via uv only (`moto` dev group; `aws-cdk-lib`+`constructs` infra group); lockfile updated | intent.md Constraints | PASS | `[dependency-groups] dev=moto>=5.2.2`, `infra=aws-cdk-lib>=2.261.0, constructs>=10.7.1`; `uv.lock` modified; no requirements.txt |
| R10 | `boto3` confined to the store adapter; portable graph unchanged | intent.md Constraints | PASS | Grep + AST test T10: only `import boto3` site is `dynamo.py`; other mentions are comments/docstrings |

## Contract Compliance
| ID | Contract Item (Behavior Guarantee) | Status | Verified By |
|---|---|---|---|
| C1 | Protocol conformance + seam (G1) | PASS | T8 (`isinstance` + end-to-end `build_graph`); empty `git diff` on graph/nodes/state/interfaces/local |
| C2 | `card_id == sha256(url)[:16]` for RawItem and Card; dedup-after-upsert excludes the batch (G2) | PASS | T1; code review of `_card_id` |
| C3 | `dedup_filter` order-preserving, only-unseen, `[]`/no-AWS on empty (G3) | PASS | T2 + empty-input `_NoCallResource` test; code returns `[]` before any AWS call |
| C4 | Upsert idempotency: 2× batch → one item/`card_id`, `created_at` stable, `updated_at` advances, no dups (G4) | PASS | T3 re-reads `created_at`/`updated_at` across two runs; `if_not_exists(created_at, :now)` in expression |
| C5 | `upsert` never writes `embedding`; pre-seeded embedding survives re-upsert (G5) | PASS | T6; grep confirms `embedding` never referenced in `dynamo.py` |
| C6 | Every item carries `gsi_pk="CARD"` + `gsi_sk=f"{relevance:03d}#{published}"`; GSI query returns score-desc/date-desc (G6) | PASS | T4, T5 (incl. dateless trailing `#`), T9 (ordering) |
| C7 | Per-card resilience: one card raising → `failures()` +1, others persist (G7) | PASS | T7; `try/except Exception` → log + `failures += 1` + `continue` |
| C8 | `boto3` imported only in `dynamo.py`; absent from nodes/graph/state/interfaces/local (G8) | PASS | T10 (AST) + independent grep |
| C9 | CDK construct: on-demand billing, `RETAIN`, `feed-by-score` GSI (projection ALL), key schema matches contract (G9) | PASS | T11 + ad-hoc `app.synth()`: `GlobalTable`, `PAY_PER_REQUEST`, PK `card_id`, GSI `gsi_pk`/`gsi_sk` proj ALL, `DeletionPolicy: Retain` |
| C10 | All store tests via `moto`, zero real-AWS; infra tests synth-only (G10) | PASS | Every store test uses `dynamo_resource`/`dynamo_table` (`mock_aws`); infra via `Template.from_stack` |
| C11 | Item schema matches contract table (all Card fields + card_id/created_at/updated_at/gsi_pk/gsi_sk; embedding absent) | PASS | T4 asserts all fields present + `embedding` absent |
| C12 | boto3/CDK API surface matches Context7-pinned signatures | PASS-with-note | `update_item`+`if_not_exists`, `batch_get_item`, `TableV2`/`Billing.on_demand()` all as pinned. See Deviation D1: `#src` placeholder added for `source` (reserved word) beyond the pinned expression string |
| C13 | Error-handling contract honored (7 rows) | PASS | See table below |

### Error Handling Contract — row-by-row
| Error Condition | Expected impl | Status |
|---|---|---|
| One card's `update_item` raises | per-card `try/except` → log, `failures += 1`, continue | PASS (T7) |
| Empty `dedup_filter`/`upsert` input | early return, no AWS call | PASS (T2 + `_NoCallResource` on both paths) |
| `batch_get_item` `UnprocessedKeys` | bounded retry (≤5), union before filter | PASS (code review; loop unions `Responses` then reassigns `UnprocessedKeys`) — see Warning W1 |
| Duplicate `card_id` in one batch | last `update_item` wins, one row | PASS (T3 duplicate-in-batch test) |
| Already-stored item across runs | `dedup_filter` excludes it | PASS (T1) |
| Missing table / creds (real backend) | boto3 raises out of store (loud) | PASS (n/a under moto; `dedup_filter`/`__init__` do not swallow connection errors — only per-card `upsert` failures are caught) |
| Reserved word `type` in expression | `ExpressionAttributeNames` placeholder | PASS (`#ty`; also `#t`/`#u`/`#src` for title/url/source) |

## Test Coverage
| ID | Test Description | Status | Test File |
|---|---|---|---|
| T1 | upsert → dedup_filter excludes persisted; `card_id` from `Card.url` == `RawItem.url_hash` | PASS (GREEN) | tests/test_dynamo_store.py |
| T2 | `dedup_filter` order-preserving, only-unseen, `[]`/no-AWS on empty (+ `upsert([])` no-AWS no-op) | PASS (GREEN) | tests/test_dynamo_store.py |
| T3 | Idempotency: 2× batch → one item/`card_id`, `created_at` stable, `updated_at` advances (+ duplicate-`card_id`-in-batch last-write-wins) | PASS (GREEN) | tests/test_dynamo_store.py |
| T4 | Item schema: all Card fields + card_id/created_at/updated_at/gsi_pk/gsi_sk; `embedding` absent; `type` handled | PASS (GREEN) | tests/test_dynamo_store.py |
| T5 | `gsi_sk == f"{relevance:03d}#{published}"`; dateless card → trailing `#` | PASS (GREEN) | tests/test_dynamo_store.py |
| T6 | No-clobber: pre-seeded `embedding` survives re-upsert | PASS (GREEN) | tests/test_dynamo_store.py |
| T7 | Resilience: one card raises in `update_item` → `failures()==1`, others persist | PASS (GREEN) | tests/test_dynamo_store.py |
| T8 | Protocol + seam: `isinstance(store, CardStore)`; `build_graph(store, FakeDiscoverer)` invokes end-to-end → cards persisted | PASS (GREEN) | tests/test_dynamo_store.py |
| T9 | GSI read-shape: `query(feed-by-score, gsi_pk=CARD, ScanIndexForward=False)` returns score-desc/date-desc | PASS (GREEN) | tests/test_dynamo_store.py |
| T10 | Portability: `boto3` only in `dynamo.py`; absent from nodes/graph/state/interfaces/local | PASS (GREEN) | tests/test_dynamo_store.py |
| T11 | CDK `Template` assertions: PAY_PER_REQUEST, `card_id` PK, `feed-by-score` GSI (gsi_pk/gsi_sk, projection ALL), DeletionPolicy Retain | PASS (GREEN) | tests/test_infra.py |
| T12 | Zero live-AWS calls in the suite (all `mock_aws` / synth-only) | PASS (GREEN, structural) | tests/test_dynamo_store.py, tests/test_infra.py |

> Full suite: `uv run pytest -v` → **43 passed, 0 failed** (27 pre-existing Spec
> 01/02 + 16 new Spec 03: 14 in `tests/test_dynamo_store.py`, 2 in
> `tests/test_infra.py`). No `skip`/`xfail`/`live` markers; no red-phase test
> weakened. Ad-hoc `app.synth()` independently confirmed the synthesized
> `AWS::DynamoDB::GlobalTable`: `PAY_PER_REQUEST`, PK `card_id`, GSI
> `feed-by-score` (`gsi_pk` HASH / `gsi_sk` RANGE, projection ALL),
> `DeletionPolicy: Retain`, and **no** `PointInTimeRecoverySpecification`.

## Deviations Log
| ID | Deviation | Severity | Blocking? | Assessment |
|---|---|---|---|---|
| D1 | `upsert`'s `UpdateExpression` adds an `ExpressionAttributeNames` placeholder `#src` → `source` not present in contract.md's pinned example (which left `source` unescaped) | LOW | No | **Legitimate fix to a contract typo.** Independently verified `source` IS a DynamoDB reserved word: an unescaped `SET source=:s` is rejected by real DynamoDB *and* moto with `ValidationException`, while `#src`→`source` is accepted. The pinned expression as written could not function; the fix is necessary for the pinned public API surface to work at all. No test asserts the literal expression string — only persisted attribute *values* (T4) — so no locked behavior is touched. Executor flagged it proactively in tasks.md Task 2.5. **Recommend a doc-only correction to contract.md** (see R1 below); no behavior change. |

## Audit Log
| Date | Auditor | Finding | Severity | Resolution |
|---|---|---|---|---|
| 2026-07-21 | sdd-auditor | Full independent audit: 43/43 tests green; all 10 Behavior Guarantees + 7 error-handling rows satisfied; key schema byte-matches across contract/CDK-synth/moto-fixture; boto3 confined to `dynamo.py`; seam files unchanged; PITR absent; on-demand + RETAIN confirmed via ad-hoc synth. | INFO | APPROVED — no blocking issues |
| 2026-07-21 | sdd-auditor | D1: `#src` placeholder for reserved word `source` added beyond contract's pinned `UpdateExpression`. Verified `source` is genuinely reserved; fix is necessary and non-breaking (no test asserts the literal string). | LOW | Non-blocking; recommend doc-only contract.md amendment (R1) |
| 2026-07-21 | sdd-auditor | W1: `dedup_filter` `UnprocessedKeys` retry is bounded at 5; keys still unprocessed after exhaustion are silently treated as absent (item returned as new → re-summarized, not lost). | LOW | Non-blocking; acceptable degradation, documentation-only |

## Final Verdict

**Status**: APPROVED

**Summary**: `DynamoCardStore` and the `CardStoreTable` CDK construct faithfully
implement Spec 03: all 10 behavior guarantees, the 7-row error-handling contract,
and the LOCKED key schema are satisfied and independently verified, with 43/43
tests green and zero real-AWS calls. The stable Spec 01 seam is byte-unchanged and
`boto3` is confined to the one infra adapter.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- **W1** — `dedup_filter`'s `UnprocessedKeys` retry is bounded at 5 iterations; if
  DynamoDB is still returning unprocessed keys after that (sustained throttling),
  those keys are silently treated as absent, so the affected items would be
  re-summarized on that run rather than deduped. This is safe (no data loss, no
  duplicates — the eventual `upsert` is idempotent) but under-documented. Consider
  a one-line comment noting the bound-exhaustion behavior. Not blocking.

**Recommendations** (nice to have):
- **R1 (doc-only)** — Amend contract.md's pinned `UpdateExpression` example (lines
  ~34-42) to escape `source` via `#src` in `ExpressionAttributeNames`, matching the
  implementation, so future readers aren't misled by the discrepancy. `source` is a
  DynamoDB reserved word (verified empirically); the current example would not
  execute as written. **Documentation change only — do not alter behavior.**
- **R2** — Task 3.2 (live smoke against a real deployed table) remains correctly
  `[!]` blocked / out-of-scope; carry it into the Spec 04/05 deploy checklist so
  the seam gets one real-backend exercise before production.

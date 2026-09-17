# Audit: run-observability

> Status: **AUDITED — Phases 1–5 on 2026-08-11, Phase 6 (live fire) re-audited
> 2026-08-12, both by `sdd-auditor`.** Phase 6 has now been **executed against
> real AWS**; T35–T40 are filled in below from the auditor's own re-derivation
> of the live evidence, not from the executor's report.
>
> **This audit has a second job.** Per the source brief
> (`tasks/phase-1-curation-mvp/06-run-observability.md` § SDD note) and
> roadmap.md Phase 6.10, the auditor's final pass must ALSO close out
> **all of Phase 1** against the *Definition of done* in
> `README.md` / `tasks/phase-1-curation-mvp/README.md` — see the dedicated
> section at the bottom. Do not sign off on this spec alone.
>
> **Auditor's own verification run (2026-08-11), not accepted from tasks.md:**
> `uv run pytest tests/` → **144 passed**, 2.49 s, no skips/xfails, no network
> (no `@pytest.mark.live` markers exist in this suite; the default run *is* the
> offline run) · `uv run --group infra cdk synth --app "python infra/app.py"` →
> all four stacks synthesize, **no `cdk.context.json` written** ·
> `cdk diff AiRadarCardStore AiRadarRuntimeRole AiRadarSchedule` → *"There were
> no differences"* on all three (**Number of stacks with differences: 0**) ·
> `git diff --stat` matches roadmap.md's File Change Map exactly, with no
> surprise files (`.bedrock_agentcore.yaml` is a pre-existing untracked CLI
> artifact, not produced by this spec) · live read-only AWS checks:
> `aws budgets describe-budgets` → only the pre-existing "My Monthly Cost
> Budget" ($1/mo) exists (`ai-radar-monthly-cost` absent ⇒ Phase 6 genuinely
> not run, and R12's pre-state recorded) · `aws cloudformation describe-stacks`
> → `AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarSchedule` live,
> **no `AiRadarBudget`** · `aws scheduler list-schedules` → the one schedule is
> still **DISABLED**.
>
> **Auditor's Phase-6 re-verification run (2026-08-12), all re-derived from
> live AWS — no claim below is accepted from the executor's report:**
> `aws budgets describe-budgets` → **two** budgets now: the untouched
> pre-existing "My Monthly Cost Budget" ($1, `IncludeCredit: null`) **and**
> `ai-radar-monthly-cost` (COST/MONTHLY/$250.0, **`IncludeCredit: false`**) ·
> `describe-notifications-for-budget` → three `ACTUAL`/`GREATER_THAN`/
> `ABSOLUTE_VALUE` at 50.0/100.0/250.0, all `NotificationState: OK` ·
> `describe-stacks AiRadarBudget` → `CREATE_COMPLETE`, created
> `2026-08-12T16:22:45Z`, all five outputs present ·
> `sns list-subscriptions-by-topic` → subscription ARN
> `…:ai-radar-budget-alerts:8b9851bd-…` (**not** `PendingConfirmation`) ·
> `sns get-topic-attributes` → the live topic policy carries both
> `AllowPublishThroughSSLOnly` (Deny) and `AllowBudgetsPublish` (Allow
> `budgets.amazonaws.com`, `aws:SourceAccount` + `ArnLike aws:SourceArn =
> arn:aws:budgets::536697225154:budget/ai-radar-monthly-cost`) ·
> `cloudwatch list-metrics --namespace AIRadar/Curation` → **exactly 4**
> metrics, `"Dimensions": []` on every one · `get-metric-statistics` on all
> four → one datapoint each (`RunsCompleted` 1, `CardsWritten` 8,
> `ItemsFailed` 0, `EstimatedCostUsd` 0.063358, Unit `None`) ·
> `logs filter-log-events` on the run's `run_id` → the full six-record
> sequence, raw · `AWS/Bedrock` `InputTokenCount`/`OutputTokenCount` for the
> run window → `Sum: 10593.0` / `2553.0`, `SampleCount: 8.0` each ·
> both pinned Logs Insights queries re-run by the auditor via
> `start-query`/`get-query-results` → `recordsMatched: 1.0`, `Complete` ·
> `dynamodb scan --select COUNT` → **80** (72 + 8) ·
> `ecr describe-images` → new tag `20260812-162922-638` pushed
> `2026-08-12T16:29:51Z`, superseding `20260810-221147-104` ·
> `agentcore status` → Ready, endpoint READY, last updated
> `2026-08-12T16:30:42Z` · `aws scheduler list-schedules` → the single
> schedule is **still `DISABLED`** · `uv run pytest tests/` → **145 passed**
> (was 144; +1 from the O1 regression case, see the Audit Log).

## Requirements Checklist

| ID | Requirement | Source | Status | Notes |
|---|---|---|---|---|
| R1 | Every successful run produces exactly one `RunSummary` covering discovered (with RSS/Tavily split), deduped, summarized, failed, cards-written, wall-clock, tokens, Tavily searches/credits, and estimated USD cost | intent.md Goal 1 | **PASS** | `src/curation/summary.py:13-45` (21 fields, all present) built once per run in `runtime_app._run_curation_pipeline` (`runtime_app.py:142-151`) and once per local run (`run_curation.py:76-86`). Verified end-to-end by `tests/test_runtime_app.py::test_run_curation_pipeline_returns_run_summary_with_run_id_and_correct_derived_fields`. |
| R2 | `RunSummary` is an immutable dataclass in `src/curation/summary.py` whose `to_dict()` keys are exactly its fields, in order | intent.md Goal 1 / Success Criteria | **PASS** | `@dataclass(frozen=True)`, `to_dict()` = `dataclasses.asdict`. Field order asserted verbatim against contract.md §2 by `test_run_summary_to_dict_keys_match_pinned_order`; immutability by `test_run_summary_is_immutable` (`FrozenInstanceError`). |
| R3 | Bedrock token usage is captured from the Converse `usage` block via a NEW `summarize_with_usage`, accumulated in `summarize_node` | intent.md Goal 2 | **PASS** | `src/spike/bedrock.py:92-131` reads `resp.get("usage", {})`; `src/curation/nodes.py:85-87` accumulates **inside** the per-item `try`, immediately after the call. `test_summarize_node_accumulates_tokens_and_bills_tokens_for_items_that_fail_after_the_call` proves an item failing in `Card.from_model` still bills its tokens. |
| R4 | `spike.bedrock.summarize()` keeps its exact signature/return type; `src/spike/{pipeline,chat}.py`, `run_spike.py`, `run_chat.py` untouched | intent.md Goal 2 / Success Criteria | **PASS** | `summarize(item) -> dict` is now `return summarize_with_usage(item)[0]` (`bedrock.py:134-139`). Auditor ran `git diff --stat HEAD -- src/spike/{pipeline,chat,retrieval,cards,feeds}.py run_spike.py run_chat.py` → **empty** (byte-identical). Plane B does not regress. |
| R5 | Cost estimation is pure arithmetic over env-overridable price constants — Bedrock in `spike/config.py` (beside `HAIKU_MODEL_ID`), Tavily in `curation/config.py` | intent.md Goal 3 | **PASS** | `spike/config.py:25-32` (`HAIKU_INPUT_USD_PER_1M=1.0` / `HAIKU_OUTPUT_USD_PER_1M=5.0`, **bare** env names per that file's convention, placed immediately after `HAIKU_MODEL_ID` — the human-review-driven placement, confirmed *not* in `curation/config.py`); `curation/config.py:71-96` (`TAVILY_CREDIT_PRICE_USD=0.008`, `{"basic":1,"advanced":2}`, fallback 1, plus the explicit "the Bedrock prices are NOT here" pointer comment). No I/O in either estimator. |
| R6 | The `curation_run_complete` record is a strict SUPERSET of the eight `async-invocation-ack` fields (no rename, no retype, no removal) | intent.md Goal 4 / Constraints | **PASS** | `runtime_app.py:179-181` logs `{"event": "curation_run_complete", **summary.to_dict()}`. All eight originals keep their names, types and values; 11 fields added. Guarded by `test_curation_run_complete_log_record_is_a_superset_of_the_eight_original_fields_plus_new_fields`, which asserts the originals' **exact values** first and the new fields second. `event` literal unchanged ⇒ README runbook + `specs/async-invocation-ack/audit.md` claims stay true. |
| R7 | `discover`, `summarize`, `persist` each emit one structured JSON record per run, joined by `run_id`; no per-item success logging | intent.md Goal 4 | **PASS** | `nodes.py:26-32` `_log()`; emitted at `:51`, `:101`, `:128`. `dedup_node`/`rank_node` are silent and otherwise untouched. `test_exactly_three_node_records_emitted_per_run_each_carrying_run_id` asserts the event list is **exactly** `[discover_complete, summarize_complete, persist_complete]` and every record carries the invoked `run_id`. |
| R8 | Run summaries are persisted as CloudWatch EMF custom metrics in `AIRadar/Curation` (4 metrics, no dimensions) — NOT a DynamoDB `runs` table | intent.md Goal 5 | **PASS (offline + live)** | `src/curation/metrics.py` builds the pinned document and writes one raw line; no `runs` table, no new table/attribute/write path anywhere in the diff. **Live (2026-08-12, auditor-run):** `list-metrics --namespace AIRadar/Curation` returns exactly the four metrics with `"Dimensions": []` on each — CloudWatch really does extract EMF from the AgentCore runtime log group, and cardinality is 4 as designed. |
| R9 | `CURATION_EMIT_METRICS=false` fully suppresses metric emission and changes nothing else | intent.md Goal 5 / Success Criteria | **PASS** | `metrics.py:87-88` early-returns `False` before touching the stream. `test_emit_run_metrics_respects_the_kill_switch` (nothing written) and `test_metrics_kill_switch_suppresses_the_emf_line_without_affecting_curation_run_complete` (the run record still appears) together cover both halves. |
| R10 | A new CDK-managed monthly cost budget `ai-radar-monthly-cost` notifies at $50/$100/$250 ACTUAL, absolute USD, with `IncludeCredit: false` | intent.md Goal 6 | **PASS (synth + deployed)** | Auditor synthesized `AiRadarBudget` directly (pre-deploy) and re-queried the **deployed** budget on 2026-08-12: `COST`/`MONTHLY`/`$250.0`/`IncludeCredit: false`, with three `ACTUAL`/`GREATER_THAN`/`ABSOLUTE_VALUE` notifications at 50.0/100.0/250.0, all `NotificationState: OK`. The synthesized template and the deployed reality agree field-for-field. |
| R11 | Notifications go to a new SNS topic with a confirmed email subscription for `danielmauricioerazoespinoza@gmail.com`, and a topic policy allowing `budgets.amazonaws.com` to publish | intent.md Goal 6 | **PASS** (was PARTIAL) | Auditor re-queried the live topic: the subscription now has a **real ARN** (`…:ai-radar-budget-alerts:8b9851bd-62d1-472a-98ee-6be5cd9e0b77`), not `PendingConfirmation` — the human's confirmation click landed. The live topic policy carries `AllowBudgetsPublish` with both conditions exactly as pinned, plus CDK's `enforce_ssl` Deny. Delivery was additionally proven end-to-end by a real `aws sns publish` the human received (T36). |
| R12 | The pre-existing, hand-made "My Monthly Cost Budget" is untouched | intent.md Goal 6 / Non-Goals | **PASS (before AND after)** | Before (2026-08-11): exactly one budget, `My Monthly Cost Budget`, COST, $1.00. After (2026-08-12, post-deploy): **two** budgets — the pre-existing one still `$1.0` / `IncludeCredit: null` (i.e. still default cost types, never rewritten), alongside `ai-radar-monthly-cost`. CloudFormation neither adopted nor modified it, exactly as the distinct-name design predicted. |
| R13 | `run_curation.py` builds and prints the same `RunSummary` locally | intent.md Goal 7 | **PASS** | `run_curation.py:76-105`: same `build_run_summary(...)` call shape as `runtime_app`, printing discovered (rss/tavily), deduped, summarized, failed, cards_written, discoverer/store failures, tokens in/out, tavily searches/credits, and all three cost figures at 6 dp. `emit_run_metrics` is deliberately **not** called (commented with the reason). |
| R14 | Observability cost stays negligible: no trace export, ≤4 custom metrics (~$1.20/mo), ~5 log records per run | intent.md Goal 7 / source spec | **PASS** | `METRIC_DEFINITIONS` is exactly 4 with `Dimensions: [[]]` (cardinality can never grow); per run: 3 node records + 1 run record + 1 EMF line + ≤`failed` warnings. No OTEL/span/trace code anywhere in the diff. |
| R15 | Portability preserved: no `boto3`/`botocore`/`bedrock_agentcore` import in `nodes.py`, `graph.py`, `state.py`, `summary.py`, `metrics.py` | intent.md Constraints | **PASS** | Auditor ran the pinned grep. It returns **two hits, both prose comments** (`nodes.py:4` and `graph.py:25`, each saying "no boto3 import here") — **zero imports**. The semantic guarantee is enforced AST-wise by `test_curation_modules_do_not_import_aws_sdk_or_bedrock_agentcore` across all five files, broadened this spec to also catch `botocore`/`bedrock_agentcore`. See finding **O3** on the literal wording of the criterion. |
| R16 | No new IAM permission and no new AWS resource for telemetry; `cdk diff` on the other three stacks is empty | intent.md Success Criteria | **PASS (pre- and post-deploy)** | Auditor-run `cdk diff` against the **live** account before the budget deploy: *"Number of stacks with differences: 0"*. Re-confirmed by the executor immediately **after** `cdk deploy AiRadarBudget` — still no differences on all three. The definitive proof is behavioural: the live run emitted 4 custom metrics using only the pre-existing `logs:PutLogEvents` grant, with **zero** `PutMetricData` permission anywhere on the execution role. |
| R17 | No new runtime dependency: `pyproject.toml` / `uv.lock` unchanged | intent.md Constraints | **PASS** | `git diff --stat HEAD -- pyproject.toml uv.lock` → empty. New code uses only stdlib (`json`, `logging`, `sys`, `time`, `uuid`, `dataclasses`, `collections.Counter`) plus `aws_cdk.aws_budgets`/`aws_sns*`, which ship inside the already-present `aws-cdk-lib`. `pydantic-settings` remains transitive-only, as the contract requires. |
| R18 | `uv run pytest tests/` stays 100% offline and green (existing suite + new tests) | intent.md Success Criteria | **PASS** | Auditor-run 2026-08-11: **144 passed** in 2.49 s (was 92 pre-spec). Re-run 2026-08-12 after the O1 hardening: **145 passed** in 2.41 s. Bedrock stubbed at `spike.bedrock.bedrock_client`, Tavily at `curation.tavily`'s namespace, DynamoDB via `moto`, CDK synth-only, EMF via `io.StringIO`. No credentials, no network, no `cdk.context.json` written. |
| R19 | **Live**: the budget is visible in the console, the email subscription is confirmed, and a real `aws sns publish` is delivered | intent.md Goal 8 / Success Criteria | **PASS** | `AiRadarBudget` → `CREATE_COMPLETE` (2026-08-12T16:22:45Z); the budget is queryable via the Budgets API (hence visible in the Billing console) with the exact designed shape; the email subscription holds a real ARN, not `PendingConfirmation`; a real `aws sns publish` (`MessageId a9b27081-…`) was delivered to and confirmed in the human's inbox. The one step no automation can do — the confirmation click — was genuinely performed. |
| R20 | **Live**: after a real invocation, `AIRadar/Curation` exposes 4 metrics with datapoints, and the enriched records appear in CloudWatch | intent.md Goal 8 / Success Criteria | **PASS** | Agent rebuilt (`20260812-162922-638`, pushed 16:29:51Z) and invoked; run `d577c1c0…`. Auditor pulled the raw log events: all six records present in order, the enriched `curation_run_complete` carrying every new field with real values (`input_tokens: 10593`, `discovered_rss: 30` + `discovered_tavily: 20` = `discovered: 50`, `estimated_cost_usd: 0.063358`), and all four metrics returning one datapoint each. See T37/T38. |
| R21 | **Live**: the documented Logs Insights query answers "failed counts for the last 7 runs" against real data | source spec acceptance criteria | **PASS** | Auditor re-ran **both** pinned queries himself against the real log group (`start-query`/`get-query-results`, 2 h window): query 1 (EMF) → `Complete`, `recordsMatched: 1.0`, with `run_id`/`discovered`/`failed`/`cards_written`/`estimated_cost_usd` returned as first-class columns with **no parsing**; query 2 (logger record) → `Complete`, `recordsMatched: 1.0`. Only one run exists so far, so `limit 7` returns 1 — the query is proven, the history is simply young. |
| R22 | Docs updated: `README.md` (spec row, observability section, runbook, live state), `.env.example` (5 knobs) | intent.md / roadmap | **PARTIAL — and now STALE, not merely incomplete** | `.env.example` (**PASS**) and the "Run observability" section, both Insights queries, the metric list and the deploy/confirm/**teardown** runbook are all present and correct. But **Task 6.11 was not performed**, so four statements in `README.md` are now factually **false**: the spec-table row still reads "🔧 Implemented, not yet deployed" and "the real `cdk deploy` + `agentcore deploy` + live-fire verification … has **not** run yet" (`:24`); "Current live AWS state (**as of 2026-08-10**)" still describes two stacks and the old image (`:406-415`); "**Status as of this writing:** Phases 1-5 … have **not** run yet" (`:485`); and the test count says 144, now 145 (`:24`, `:498`). See finding **F1**. |

## Contract Compliance

| ID | Contract Item | Status | Verified By |
|---|---|---|---|
| C1 | `TokenUsage` frozen dataclass + `summarize_with_usage(item) -> tuple[dict, TokenUsage]` in `src/spike/bedrock.py` | **PASS** | Read `bedrock.py:16-28, 92-131`: signature, return type, defaults (`0, 0`) and docstring match contract §1 verbatim. `test_summarize_with_usage_returns_card_dict_and_token_usage_from_converse_response`. |
| C2 | `summarize(item) -> dict` unchanged, implemented as `summarize_with_usage(item)[0]` | **PASS** | `bedrock.py:134-139` is literally that one line. `test_summarize_returns_same_dict_as_summarize_with_usage_first_element` also asserts `isinstance(result, dict)` (not a tuple). Diff shows the Converse call body moved verbatim — no inference-config or prompt drift. |
| C3 | Missing/malformed `usage` degrades to `TokenUsage(0, 0)` (Error Handling row 1) | **PASS** (with **O1** noted) | `bedrock.py:119-126`: `resp.get("usage", {}) or {}` + `except (TypeError, ValueError)`. Parametrized `test_summarize_with_usage_degrades_to_zero_usage_on_missing_or_malformed_usage_block[missing|empty|non-int-values]`. A *non-mapping* `usage` value would raise `AttributeError` — outside the row's pinned wording; see finding **O1**. |
| C4 | `RunSummary` field set + order exactly as pinned in contract.md §2 | **PASS** | Field-by-field diff against contract §2 by the auditor: 21 fields, identical names, types, order and inline comments. `test_run_summary_to_dict_keys_match_pinned_order` pins the order as a hard-coded list. |
| C5 | `split_by_origin` classifies by `config.TAVILY_SOURCE_PREFIX`; `summary.py` never imports `curation.tavily` | **PASS** | `summary.py:48-64`, prefix-based. `test_summary_module_does_not_import_the_tavily_sdk_or_curation_tavily` walks the module's AST and asserts `tavily` is not among the import roots (not a vacuous string check). |
| C6 | `estimate_bedrock_cost_usd` reads `spike_config.HAIKU_{INPUT,OUTPUT}_USD_PER_1M` and `estimate_tavily_cost_usd` reads `config.TAVILY_CREDIT_PRICE_USD` — both via the module object at call time; round to 6 dp; `0.0` for zero input | **PASS** | `summary.py:67-84` uses `spike_config.X` / `config.X` attribute access (never `from … import X`), so the two monkeypatch tests (`…reads_prices_from_spike_config_at_call_time`, `…reads_price_from_curation_config_at_call_time`) genuinely bite. `round(..., 6)`; `(0,0) -> 0.0` and `0 -> 0.0` asserted. |
| C7 | `build_run_summary` reads `state` defensively and derives `cards_written = max(persisted - store_failures, 0)` | **PASS** | `summary.py:107-119`: every read is `.get(..., 0)` / `.get(..., {})`; `max(persisted - store_failures, 0)` at `:112`. `test_build_run_summary_on_empty_state_returns_zeros_without_raising` (`state={}`) and `…clamps_cards_written_at_zero_when_store_failures_exceed_persisted` (3 persisted, 10 failures → 0). |
| C8 | Guarantee 3 identities: `discovered_rss + discovered_tavily == discovered == sum(discovered_by_source.values())`; costs sum | **PASS** | Identities hold by construction (`discovered = len(raw)`, `discovered_by_source = Counter(item.source …)`, rollup from the same dict; `estimated_cost_usd = round(bedrock + tavily, 6)`). Asserted at summary level (`test_build_run_summary_full_state_satisfies_counter_identities_and_cost_sum`), at graph level (`test_discover_node_groups_raw_items_by_source_into_discovered_by_source`) and at record level (T22's cost-sum `pytest.approx`). |
| C9 | `run_metrics_document` emits the pinned EMF shape (`_aws.Timestamp`, `Namespace`, `Dimensions: [[]]`, the 4 `Metrics`, summary payload, PascalCase targets) | **PASS** | `metrics.py:33-68`. `test_run_metrics_document_matches_pinned_emf_shape` compares `_aws` as a whole dict, checks every summary field is present at the root with its value, checks the four PascalCase targets, **and** asserts `set(doc.keys())` is exactly the expected set — so a stray or missing field fails. `test_run_metrics_document_defaults_timestamp_to_now_when_unset` pins the `int(time.time()*1000)` default. |
| C10 | `emit_run_metrics` writes ONE raw JSON line + `\n` to `sys.stderr` (resolved at call time), flushes, returns `bool`, and never goes through `logging` | **PASS** | `metrics.py:71-96`: `stream=None` → `sys.stderr` resolved *inside* the body; single `stream.write(json.dumps(doc) + "\n")` + `flush()`. Three targeted tests: exactly one `\n`-terminated line that round-trips through `json.loads` with nothing before/after; `caplog.records == []` at DEBUG (the "someone tidies it into a logger call" regression guard); and a `monkeypatch.setattr(sys, "stderr", …)` test that would fail if the default were bound at import. |
| C11 | `METRIC_DEFINITIONS` has exactly 4 entries and `EMF_DIMENSIONS == [[]]` (Guarantee 8 — cardinality can never grow) | **PASS** | `metrics.py:18-28` with the "never add a dimension" comment intact. `test_emf_dimensions_and_metric_definitions_are_bounded_by_contract` asserts both the count and the exact name set. |
| C12 | `CurationState` gains exactly `run_id`, `discovered_by_source`, `persisted`, `input_tokens`, `output_tokens`; no reducers; existing keys unchanged | **PASS** | `state.py` diff adds exactly those five keys and flips the comment "consumed by Spec 06 later" → "consumed by Spec 06". No `Annotated`/reducer anywhere; every new key is written by exactly one node, so last-write-wins remains correct. |
| C13 | `discover_node` returns `discovered_by_source` grouped by `RawItem.source` | **PASS** | `nodes.py:50` `dict(Counter(item.source for item in raw))`. T14 asserts the grouping and that it sums to `discovered`. |
| C14 | `summarize_node` accumulates usage inside the existing per-item `try`, immediately after the call (tokens billed even if `Card.from_model` fails) | **PASS** | `nodes.py:84-88` — accumulation is on the two lines *between* the call and `Card.from_model`. T15 constructs an item whose `relevance` breaks `Card.from_model` **after** usage was returned and asserts the failed item's 50/10 tokens are still counted. |
| C15 | Per-item failure is a structured `logger.warning` (`summarize_item_failed` with `url` + `error`), replacing the `print` | **PASS** | `nodes.py:89-100`; the old `print(f"  ! failed to summarize …")` is gone from the diff. T18 asserts exactly one WARNING record with `event`/`url`/`error`. |
| C16 | `persist_node` returns `{"persisted": len(cards)}`; `dedup_node` / `rank_node` unchanged and log nothing | **PASS** | `nodes.py:124-131` returns the count (was `{}`); `dedup_node` (`:66-74`) and `rank_node` (`:118-121`) are byte-identical in the diff and emit nothing. T16 + T17 (the three-record list is exact, so a fourth record would fail). |
| C17 | `TavilyDiscoverer.searches()` counts ATTEMPTED seeds (including failures) and resets per `discover()`; `credits_used()` uses the depth map with a 1-credit fallback | **PASS** | `tavily.py`: `self._searches = 0` reset at `discover()` start (beside the existing `_failures` reset), `+= 1` **before** the `try`, so a raising seed is still counted. `test_searches_counts_attempted_seeds_including_failures_and_resets_per_discover` (2 then 1, not 3) and the 4-way parametrized `test_credits_used_maps_search_depth_to_credits_with_fallback[basic/advanced/fast/ultra-fast]`. |
| C18 | `CompositeDiscoverer.searches()` / `credits_used()` are duck-typed sums defaulting to 0; `composite.py` still imports no `tavily`/`boto3` | **PASS** | `composite.py:53-61`, `hasattr`-guarded generator sums; no new import (the pre-existing `test_tavily_sdk_imported_only_in_tavily_module_no_boto3_anywhere` AST test still passes). `test_composite_searches_and_credits_used_sum_sources_defaulting_to_zero` mixes a stats-bearing source with a plain one. |
| C19 | `TavilyDiscoverer`'s source label is byte-identical after switching to the shared prefix constant | **PASS** | `f"Tavily: {self.topic}"` → `f"{config.TAVILY_SOURCE_PREFIX}{self.topic}"` with `TAVILY_SOURCE_PREFIX = "Tavily: "`. Byte-identity is proven by the **unmodified** pre-existing assertion `assert item.source == "Tavily: general"` (`tests/test_tavily.py:88`) still passing, and the new T21 test proves the value is genuinely *derived from* the constant (monkeypatching it to `"Custom: "` changes the label), so a re-hardcoded literal would be caught. |
| C20 | `_configure_curation_logging()` attaches the SDK logger's handlers to the `curation` tree at INFO, once at import | **PASS** | `runtime_app.py:62-77`: sets the `curation` logger to INFO, copies `app.logger.handlers`, and is invoked exactly once at module scope. `test_configure_curation_logging_attaches_a_handler_and_info_level_to_the_curation_logger` (with save/restore, so it does not leak). Node modules stay infra-ignorant (`logging.getLogger(__name__)` only). |
| C21 | `_run_curation_pipeline(run_id) -> RunSummary` passes `{"max_items", "run_id"}` into the unchanged compiled graph and times itself | **PASS** | `runtime_app.py:124-151`; `time.monotonic()` brackets `graph.invoke` only. T23 asserts `invoke_calls == [{"max_items": 42, "run_id": "test-run-id"}]` plus every derived field; T3's updated test asserts the ack's `run_id` is the one that reaches the graph. `build_graph` itself is untouched (`git diff` on `src/curation/graph.py` is empty). |
| C22 | `_curation_run` logs `{"event": "curation_run_complete", **summary.to_dict()}` and then calls `emit_run_metrics` in its OWN try/except | **PASS** | `runtime_app.py:179-198`: the metrics call sits in a nested `try/except` that logs `curation_metrics_failed` at WARNING and swallows. T25 injects a raising `emit_run_metrics` and asserts `curation_run_complete` is still emitted, `curation_metrics_failed` is present at WARNING with the right `run_id`, and `curation_run_failed` is **absent**. |
| C23 | `curation_run_failed` / `curation_run_accepted` / the ack shapes / single-flight guard are unchanged from `async-invocation-ack` | **PASS** | The `except`/`finally` block, `handler`, `_active_run_id`, `_background_tasks`, `add_async_task`/`complete_async_task` bookkeeping and both ack dicts are untouched in the diff. The whole inherited `async-invocation-ack` test set still passes unchanged, and T26 additionally proves a failing pipeline never calls `emit_run_metrics`. |
| C24 | `run_curation.py` prints the summary and does NOT call `emit_run_metrics` | **PASS** | `run_curation.py:76-105`; no `emit_run_metrics` import or call anywhere in the file (grep-verified), with an inline comment stating why. `logging.basicConfig(level=INFO, format="%(message)s")` at `:52` makes the three node records print locally. |
| C25 | `CostBudget` synthesizes one `AWS::Budgets::Budget` (`COST`/`MONTHLY`, `budget_name` = `ai-radar-monthly-cost`, limit $250, `IncludeCredit: false`) | **PASS** | Auditor read the synthesized template directly (not only the test): exactly one budget resource, all four properties as pinned, and the full explicit `CostTypes` block (`IncludeRefund: false`, `UseAmortized/UseBlended: false`, the rest `true`). T29. |
| C26 | Three notifications: `ACTUAL` / `GREATER_THAN` / `ABSOLUTE_VALUE` at 50, 100, 250, each with one SNS subscriber = the stack's topic | **PASS** | Template shows three `NotificationsWithSubscribers` entries, each with a single subscriber `{"Address": {"Ref": <topic>}, "SubscriptionType": "SNS"}`. T30 asserts the sorted thresholds and resolves the `Ref` against the one topic's logical id. |
| C27 | An `AWS::SNS::TopicPolicy` allows `budgets.amazonaws.com` `sns:Publish`, scoped by `aws:SourceAccount` + `aws:SourceArn` (the budget ARN) | **PASS** | Template statement `Sid: AllowBudgetsPublish`, `Principal.Service: budgets.amazonaws.com`, `StringEquals aws:SourceAccount: {Ref: AWS::AccountId}`, `ArnLike aws:SourceArn: arn:aws:budgets::<acct>:budget/ai-radar-monthly-cost` — a literal join, so no circular reference. T31. |
| C28 | The budget `DependsOn` the topic policy (`node.add_dependency(policy_dependable)`) | **PASS** | Template's budget resource carries `DependsOn: [CostBudgetBudgetAlertsPolicy18321BFD]`. `test_budget_depends_on_the_topic_policy` resolves both logical ids rather than hard-coding them. |
| C29 | One `AWS::SNS::Subscription` of protocol `email` for the pinned address | **PASS** | Exactly one subscription, `Protocol: email`, `Endpoint: danielmauricioerazoespinoza@gmail.com`. T32. |
| C30 | `CostBudgetStack` honours `-c budget_limit_usd / budget_thresholds_usd / budget_email / budget_name` and emits the five `CfnOutput`s | **PASS** | `cost_budget_stack.py:29-53`, including the comma-string parse for thresholds. T33 (`500`, `"100,250,400"`, custom name + email all land) and `test_stack_emits_all_five_outputs`. |
| C31 | `infra/app.py` wires `CostBudgetStack(app, "AiRadarBudget")` alongside the existing three stacks, which are otherwise untouched | **PASS** | `infra/app.py` diff is exactly one import + one line. The three pre-existing stacks are byte-identical in code (`git diff` on `infra/lib/{card_store,agent_runtime,curation_schedule}.py` and their stacks is empty) **and** in the live account (`cdk diff` → no differences). |
| C32 | Guarantee 14: no Plane B import, no `Card` change, no new Protocol/aggregate/repository/domain event | **PASS** | `src/spike/{chat,retrieval,cards,feeds,pipeline}.py` are byte-identical; `summary.py`/`metrics.py` import only `spike.config`, `curation.config`, and stdlib. No new `Protocol` was added (`interfaces.py` untouched); the two new modules are plain function/dataclass modules, not a domain layer. |

## Test Coverage

Statuses below are the auditor's own verdicts, replacing the test-writer's
`WRITTEN`. Every T1–T34 row was located as a real, currently-passing test in
the green suite (144 on 2026-08-11, 145 after the O1 hardening on 2026-08-12).
T35–T40 are **manual live-fire checks, not automated tests** — each was
re-derived by the auditor from live AWS on 2026-08-12, never accepted from the
executor's report.

| ID | Test Description | Status | Test File |
|---|---|---|---|
| T1 | `summarize_with_usage` returns the tool-call dict AND `TokenUsage(inputTokens, outputTokens)` from a fake Converse response | **PASS** | `tests/test_bedrock_usage.py::test_summarize_with_usage_returns_card_dict_and_token_usage_from_converse_response` |
| T2 | A response with no `usage` block (or junk values) yields `TokenUsage(0, 0)` and does not raise | **PASS** | `tests/test_bedrock_usage.py::…degrades_to_zero_usage_on_missing_or_malformed_usage_block` (3 params: missing / empty / non-int). See **O1** for the untested non-mapping case. |
| T3 | `summarize()` returns exactly the same dict as before (back-compat, C2) | **PASS** | `tests/test_bedrock_usage.py::test_summarize_returns_same_dict_as_summarize_with_usage_first_element` (+ `…raises_runtime_error_when_no_tool_use_block` pins the unchanged failure mode) |
| T4 | `estimate_bedrock_cost_usd` matches hand-computed design-§7 values; `(0, 0) -> 0.0`; monkeypatched prices are honoured | **PASS** | `tests/test_run_summary.py::test_estimate_bedrock_cost_usd_matches_design_prices_and_zero_case`, `…reads_prices_from_spike_config_at_call_time` |
| T5 | `estimate_tavily_cost_usd`: `credits * price`, `0 -> 0.0`, monkeypatched price honoured | **PASS** | `tests/test_run_summary.py::test_estimate_tavily_cost_usd_matches_price_and_zero_case`, `…reads_price_from_curation_config_at_call_time` |
| T6 | `split_by_origin` splits `Tavily: *` from RSS feed names; empty dict -> `(0, 0)` | **PASS** | `tests/test_run_summary.py::test_split_by_origin_splits_tavily_prefixed_sources_from_everything_else`, `…empty_mapping_returns_zero_zero` |
| T7 | `build_run_summary` on a full state satisfies every Guarantee-3 identity, including `cards_written` clamping at 0 | **PASS** | `tests/test_run_summary.py::test_build_run_summary_full_state_satisfies_counter_identities_and_cost_sum`, `…clamps_cards_written_at_zero_when_store_failures_exceed_persisted` |
| T8 | `build_run_summary` on an EMPTY/partial state returns all-zero fields without raising | **PASS** | `tests/test_run_summary.py::test_build_run_summary_on_empty_state_returns_zeros_without_raising` (asserts all 15 numeric/bool fields) |
| T9 | `RunSummary.to_dict()` key list and order match contract.md §2 exactly | **PASS** | `tests/test_run_summary.py::test_run_summary_to_dict_keys_match_pinned_order` (+ `test_run_summary_is_immutable`) |
| T10 | `run_metrics_document` matches the pinned EMF shape; the 4 metric target members exist at the root with the right values | **PASS** | `tests/test_run_summary.py::test_run_metrics_document_matches_pinned_emf_shape` (exact key-set assertion), `…defaults_timestamp_to_now_when_unset` |
| T11 | `EMF_DIMENSIONS == [[]]` and `len(METRIC_DEFINITIONS) == 4` — the cardinality guard (C11) | **PASS** | `tests/test_run_summary.py::test_emf_dimensions_and_metric_definitions_are_bounded_by_contract` |
| T12 | `emit_run_metrics` writes exactly one line to the injected stream, that line is valid JSON with nothing before/after it, and it ends with `\n` | **PASS** | `tests/test_run_summary.py::test_emit_run_metrics_writes_exactly_one_valid_json_line_ending_in_newline` (+ `…never_touches_the_logging_module`, `…default_stream_is_resolved_at_call_time_not_import_time`) |
| T13 | `CURATION_EMIT_METRICS=false` ⇒ `emit_run_metrics` returns `False` and writes nothing (R9) | **PASS** | `tests/test_run_summary.py::test_emit_run_metrics_respects_the_kill_switch` |
| T14 | Graph run: `discovered_by_source` is grouped by source and sums to `discovered` | **PASS** | `tests/test_graph.py::test_discover_node_groups_raw_items_by_source_into_discovered_by_source` |
| T15 | Graph run: `input_tokens` / `output_tokens` are the sum over summarized items; a failing item still bills its tokens if the call succeeded | **PASS** | `tests/test_graph.py::test_summarize_node_accumulates_tokens_and_bills_tokens_for_items_that_fail_after_the_call` |
| T16 | Graph run: `persisted` comes from `persist_node`; `summarized + failed == len(fresh)` still holds | **PASS** | `tests/test_graph.py::test_persist_node_returns_persisted_count_matching_len_cards` |
| T17 | Exactly three node records (`discover_complete`, `summarize_complete`, `persist_complete`) per run, each carrying the invoked `run_id`; no per-successful-item record (Guarantee 7) | **PASS** | `tests/test_graph.py::test_exactly_three_node_records_emitted_per_run_each_carrying_run_id` (asserts the event **list**, so a 4th record fails) |
| T18 | A failing item emits exactly one `summarize_item_failed` warning with `url` + `error` | **PASS** | `tests/test_graph.py::test_summarize_item_failure_emits_one_warning_with_url_and_error` |
| T19 | `TavilyDiscoverer.searches()` counts attempted seeds incl. failures and resets per `discover()`; `credits_used()` = 1×/2×/fallback by depth | **PASS** | `tests/test_tavily.py::test_searches_counts_attempted_seeds_including_failures_and_resets_per_discover`, `…test_credits_used_maps_search_depth_to_credits_with_fallback` (4 params) |
| T20 | `CompositeDiscoverer.searches()` / `credits_used()` sum over sources and return 0 for sources lacking the methods | **PASS** | `tests/test_composite.py::test_composite_searches_and_credits_used_sum_sources_defaulting_to_zero`, `…reset_on_each_discover_call` |
| T21 | The Tavily source label is unchanged after the prefix-constant refactor (C19) | **PASS** | `tests/test_tavily.py::test_source_label_is_built_from_the_shared_tavily_source_prefix_constant` **plus** the untouched byte-identity assertion at `tests/test_tavily.py:88` (`item.source == "Tavily: general"`) |
| T22 | `curation_run_complete` contains all eight original fields **with unchanged values** plus every new field (R6/Guarantee 2) | **PASS** | `tests/test_runtime_app.py::test_curation_run_complete_log_record_is_a_superset_of_the_eight_original_fields_plus_new_fields` |
| T23 | `_run_curation_pipeline(run_id)` returns a `RunSummary` and invokes the graph once with `{"max_items", "run_id"}` | **PASS** | `tests/test_runtime_app.py::test_run_curation_pipeline_returns_run_summary_with_run_id_and_correct_derived_fields` (asserts `isinstance(..., RunSummary)` against the real class) |
| T24 | A successful run emits exactly one EMF line; a run with metrics disabled emits none | **PASS** | `tests/test_runtime_app.py::test_successful_run_emits_exactly_one_emf_line_to_stderr`, `…test_metrics_kill_switch_suppresses_the_emf_line_without_affecting_curation_run_complete` |
| T25 | A raising `emit_run_metrics` produces `curation_metrics_failed` (WARNING) and still `curation_run_complete` — never `curation_run_failed` (C22) | **PASS** | `tests/test_runtime_app.py::test_raising_emit_run_metrics_logs_curation_metrics_failed_and_keeps_curation_run_complete` |
| T26 | A failing pipeline still logs `curation_run_failed` with a stack trace and emits no metrics (C23 regression) | **PASS** | `tests/test_runtime_app.py::test_failing_pipeline_never_calls_emit_run_metrics` (+ the inherited, unchanged `test_curation_run_failed_logged_with_exception_info_on_pipeline_failure`) |
| T27 | `_configure_curation_logging()` leaves `logging.getLogger("curation")` with a handler and INFO level (C20) | **PASS** | `tests/test_runtime_app.py::test_configure_curation_logging_attaches_a_handler_and_info_level_to_the_curation_logger` |
| T28 | Portability grep: no `boto3`/`botocore`/`bedrock_agentcore` in `nodes.py`, `graph.py`, `state.py`, `summary.py`, `metrics.py` (R15) | **PASS** | `tests/test_graph.py::test_curation_modules_do_not_import_aws_sdk_or_bedrock_agentcore` (AST-based, all five files, all three forbidden roots) |
| T29 | Budget stack: exactly one `AWS::Budgets::Budget` named `ai-radar-monthly-cost`, `COST`/`MONTHLY`, limit 250 USD, `IncludeCredit: false` | **PASS** | `tests/test_infra_cost_budget.py::test_budget_resource_shape_name_type_limit_and_include_credit_false` — independently corroborated by the auditor's own `cdk synth AiRadarBudget` |
| T30 | Three `ACTUAL`/`GREATER_THAN`/`ABSOLUTE_VALUE` notifications at 50/100/250, each subscribed to the topic ARN with `SubscriptionType: SNS` | **PASS** | `tests/test_infra_cost_budget.py::test_three_actual_absolute_notifications_at_50_100_250_subscribed_to_the_topic` |
| T31 | The topic policy grants `sns:Publish` to `budgets.amazonaws.com` with `aws:SourceAccount` + `aws:SourceArn` conditions, and the budget `DependsOn` it | **PASS** | `tests/test_infra_cost_budget.py::test_topic_policy_grants_budgets_publish_scoped_by_source_account_and_arn`, `…test_budget_depends_on_the_topic_policy` (+ `…test_topic_enforces_ssl_with_a_deny_non_tls_statement`) |
| T32 | One `AWS::SNS::Subscription`, protocol `email`, the pinned address | **PASS** | `tests/test_infra_cost_budget.py::test_one_email_subscription_to_the_pinned_default_address` |
| T33 | Context overrides (`budget_limit_usd`, `budget_thresholds_usd`, `budget_email`) change exactly the expected template values; all five outputs present | **PASS** | `tests/test_infra_cost_budget.py::test_context_overrides_change_budget_name_limit_thresholds_and_email`, `…test_stack_emits_all_five_outputs` |
| T34 | The budget stack creates no scope-creep resources (no CloudWatch alarm, no DynamoDB table, no Lambda) | **PASS** | `tests/test_infra_cost_budget.py::test_stack_creates_no_scope_creep_resources` |
| T35 | **Live**: budget + notifications present via `aws budgets describe-budget` / `describe-notifications-for-budget`; pre-existing budget untouched (R12/R19) | **PASS** | manual runbook (roadmap 6.1–6.2), auditor re-derived 2026-08-12. `describe-budgets` → `ai-radar-monthly-cost`: `COST` / `MONTHLY` / `$250.0` / **`IncludeCredit: false`**. `describe-notifications-for-budget` → three notifications, all `ACTUAL` / `GREATER_THAN` / `ABSOLUTE_VALUE` at `50.0`, `100.0`, `250.0`, each `NotificationState: OK`. Pre-existing "My Monthly Cost Budget" still `$1.0` with `IncludeCredit: null` — untouched. `describe-stacks AiRadarBudget` → `CREATE_COMPLETE`, 5/5 outputs. |
| T36 | **Live**: SNS subscription confirmed and a manual `aws sns publish` is delivered to the inbox (R11/R19) | **PASS** | manual runbook (roadmap 6.3). Auditor re-queried `list-subscriptions-by-topic`: `SubscriptionArn = arn:aws:sns:us-east-1:536697225154:ai-radar-budget-alerts:8b9851bd-62d1-472a-98ee-6be5cd9e0b77` — a real ARN, so the confirmation click happened (it read `PendingConfirmation` beforehand). `get-topic-attributes` shows the live policy with `AllowBudgetsPublish` + both conditions. Delivery proven by `aws sns publish` (`MessageId a9b27081-f3e0-5607-8550-127752abef30`), receipt confirmed by the human. **This closes the single most likely silent-failure mode in the whole spec.** |
| T37 | **Live**: after one real invocation, `aws cloudwatch list-metrics --namespace AIRadar/Curation` returns 4 metrics with datapoints (R8/R20) | **PASS** | manual runbook (roadmap 6.5), auditor re-derived. `list-metrics` → exactly 4: `RunsCompleted`, `CardsWritten`, `ItemsFailed`, `EstimatedCostUsd`, each with `"Dimensions": []` (Guarantee 8 proven in the real account, not just in a unit test). `get-metric-statistics` on all four → one datapoint each at `16:00Z`: `RunsCompleted Sum 1.0`, `CardsWritten Sum 8.0`, `ItemsFailed Sum 0.0`, `EstimatedCostUsd Sum 0.063358 / Maximum 0.063358 / Unit None` — every value an exact match to the log record. |
| T38 | **Live**: the enriched `curation_run_complete` + the top-level EMF event + the three node records are all present for the run's `run_id` (R20) | **PASS** | manual runbook (roadmap 6.5). Auditor pulled the raw events for `run_id d577c1c0c1a240edabb5b6d461a15c07` and read them unrendered. **Exactly six records, in order:** `curation_run_accepted` → `discover_complete` (6 RSS feeds × 5 + `"Tavily: general": 20`) → `summarize_complete` (8/0, 10593/2553) → `persist_complete` (8) → `curation_run_complete` → the EMF line; **zero** warnings (`failed: 0`) — Guarantee 7's bound holds exactly. **The decisive detail:** the five logger records are each wrapped as `{"timestamp","level","message":"<escaped JSON string>","logger","requestId","sessionId"}`, while the EMF record's message is `{"_aws": {...}, "event": "curation_run_metrics", ...}` **directly at the top level, with no wrapper**. Both offline-unverifiable risks are settled in one observation: the raw stderr write lands as its **own** log event, and it genuinely bypasses `RequestContextFormatter`. All identities re-checked by the auditor against the real payload: `30 + 20 = 50 = discovered` ✓, `discovered_by_source` sums to 50 ✓, `cards_written 8 = persisted 8 − store_failures 0` ✓, `0.063358 = 0.023358 + 0.04` ✓, `summarized 8 + failed 0 = len(fresh)` ✓. |
| T39 | **Live**: the pinned Logs Insights query answers "failed counts for the last 7 runs" (R21) | **PASS** | manual runbook (roadmap 6.6). Auditor ran **both** pinned queries personally. Query 1 (`filter event = "curation_run_metrics"`) → `status: Complete`, `recordsMatched: 1.0`, returning `run_id`, `discovered: 50`, `failed: 0`, `cards_written: 8`, `estimated_cost_usd: 0.063358` as **auto-discovered top-level columns** — the payoff of the EMF-line design over the nested logger record. Query 2 (`@message like /curation_run_complete/`) → `Complete`, `recordsMatched: 1.0`, i.e. the kill-switch fallback path also works. `limit 7` returns 1 because only one instrumented run exists; the query is proven, the history is young. |
| T40 | **Live**: `estimated_bedrock_cost_usd` is within an order of magnitude of Bedrock's own reported usage for the run (sanity, not exactness) | **PASS — far exceeds the bar** | manual runbook (roadmap 6.7). Auditor independently queried `AWS/Bedrock` `InputTokenCount` / `OutputTokenCount` (dimension `ModelId = us.anthropic.claude-haiku-4-5-20251001-v1:0`) over the run window: `Sum: 10593.0` / `Sum: 2553.0`, `SampleCount: 8.0` on each — **exactly** the `input_tokens`/`output_tokens` the run reported, over exactly the 8 expected model calls. Recomputed by hand: `10593/1e6 × $1 + 2553/1e6 × $5 = $0.023358` = `estimated_bedrock_cost_usd` to the cent-fraction. **Delta $0.00.** The roadmap accepted an order-of-magnitude match; the Bedrock figure is not an estimate at all but a measurement, corroborated by AWS's own meter. (The Tavily component remains a genuine estimate — see finding **F3**.) |

## Phase 1 close-out (auditor's second pass)

Walk `tasks/phase-1-curation-mvp/README.md` § *Definition of done* and
`README.md`'s status table; cite evidence per box and record gaps here.

**Note on the source of truth:** `README.md` has no "Definition of done"
section of its own — it carries the per-spec **status table** (`README.md:16-24`)
and the "Current live AWS state" note (`:406-415`). The eight-box list lives
only in `tasks/phase-1-curation-mvp/README.md:115-124`, where **all eight
boxes are still unchecked**; the table below is the auditor's evidence-based
assessment of each, not a claim that the file was ticked.

| # | Definition-of-done item | Status | Evidence / gap |
|---|---|---|---|
| P1 | Curation loop is a LangGraph graph, logic portable (no infra coupling in node functions) | **PASS** | `specs/curation-graph/audit.md` Final Verdict **APPROVED** (9/9 guarantees). Re-verified today and *strengthened* by this spec: the portability test now covers 5 modules × 3 forbidden roots (T28), and `src/curation/graph.py` is byte-identical through six specs. |
| P2 | Discovery pulls from RSS **and** Tavily, deduped across sources | **PASS** | `specs/tavily-discovery/audit.md` **APPROVED**. Live-corroborated: the 2026-08-10 runs wrote cards from both origins; this spec now makes the split *measurable* (`discovered_rss`/`discovered_tavily`/`discovered_by_source`) rather than inferred. |
| P3 | Graph writes deduped, ranked cards to DynamoDB; re-runs idempotent | **PARTIAL** | `specs/dynamodb-card-store/audit.md` **APPROVED** offline; live idempotency has strong *incidental* evidence (the F5 double-delivery on 2026-08-10 produced 16 distinct URLs with run 1's rows untouched, `specs/eventbridge-schedule/audit.md` R12). **Gap unchanged:** the prescribed double-fire dedup drill (Spec 05 Task 4.7) has still never been run as its own test. Pre-existing; not created by, and not in scope for, this spec. |
| P4 | Graph deployed to AgentCore Runtime and invocable | **PASS** | `specs/runtime-packaging/audit.md` **APPROVED** for offline scope + a real 2026-07-28 deploy. **Refreshed 2026-08-12:** `agentcore deploy` rebuilt the image to `20260812-162922-638` (ECR push `16:29:51Z`, superseding `20260810-221147-104`); `agentcore status` → Ready, endpoint READY, last updated `16:30:42Z`; a real `agentcore invoke '{}'` returned the ack and completed a full run. The earlier ⚠️ (production running a pre-spec image) is **resolved**. |
| P5 | EventBridge Scheduler invokes it daily with no human in the loop | **PARTIAL — deliberately not upgraded** | `specs/eventbridge-schedule/audit.md`'s Phase-4 re-audit proves a real Scheduler → Runtime fire, and `async-invocation-ack` proves exactly-once after the F5 fix. **The 2026-08-12 live fire does NOT advance this box:** it was a **manual `agentcore invoke`**, not a scheduler-triggered run, so it exercises the runtime path, not the *unattended* path. Re-verified live today: `aws scheduler list-schedules` → the single schedule is **still `DISABLED`**. "Daily, with no human in the loop" therefore still rests on one-shot fires; **no full unattended day has ever elapsed**. Enabling it remains a human cost/ops go/no-go, unchanged by this spec. |
| P6 | Each run emits structured logs + a run-summary (counts, tokens/cost) to CloudWatch | **PASS — this spec, live-fire proven** | The one previously-unchecked Definition-of-done box, now closed with evidence the auditor re-derived himself: a real run (`d577c1c0…`) produced three structured node records **plus** an enriched `curation_run_complete` **plus** an EMF line in CloudWatch, yielding 4 custom metrics with datapoints; both pinned Logs Insights queries answer the acceptance question against real data; and the run's token/cost figures match AWS's own Bedrock meter **exactly** (10593/2553, delta $0.00). Counts *and* tokens/cost, structured, durable, queryable — the full text of the box. |
| P7 | All infra reproducible from code (CDK + starter toolkit), teardown documented | **PASS** | All four stacks synthesize from `infra/app.py` with no credentials and no `cdk.context.json`, and `AiRadarBudget` is now **deployed from that code** (`CREATE_COMPLETE` in ~15 s, 5/5 outputs) — reproducibility demonstrated, not just asserted. Teardown is documented per stack in `README.md`, including the two hard-won gotchas (`execution_role: null` before `agentcore destroy`; `cdk destroy AiRadarBudget`, with the note that the hand-made budget survives). |
| P8 | Cost stays within the lean-MVP envelope (design §7); no OpenSearch Serverless | **PASS — guardrail now armed** | No OpenSearch/Bedrock-KB vector backing anywhere in the repo. The feedback loop is now live: per-run `estimated_cost_usd` in logs **and** as a CloudWatch metric, 4 metrics total (~$1.20/mo) with a kill switch, and the design-§7 budget **deployed** with a **confirmed** email subscriber. The intent.md problem statement ("nothing watches the AWS bill") is closed in the account, not just in code. Live datum: the new budget reports `ActualSpend $5.382` against a $250 limit, all three thresholds `OK`; one bounded run costs `$0.063358`. |

**Phase 1 summary after the live fire: 6 of 8 boxes PASS, 2 PARTIAL (P3, P5).**
Both remaining gaps are *operational verification* gaps inherited from Spec 05,
not defects in any shipped code, and neither is in `run-observability`'s scope.
P6 — the box this spec exists to close, and the only one that was still
unchecked when the spec began — is **closed with live evidence**.

Known Phase-1 claims that were never verified (carried forward — all three
**still open**, all three pre-date this spec and are outside its scope; the
2026-08-12 live fire did not touch any of them, because a single manual invoke
exercises none of the three):
- the prescribed **double-fire dedup drill** (`specs/eventbridge-schedule`
  R12/T17, Task 4.7) was never run as its own test — only incidental,
  auditor-derived evidence from the F5 double-delivery exists;
- **`already_running`** has never been observed against the deployed agent
  (`specs/async-invocation-ack/audit.md` Task 4.4 gap) — offline tests + one
  in-process E2E only;
- the daily cadence has **never actually run unattended for a full day** —
  re-confirmed live on **2026-08-12**: the schedule is still `DISABLED`, so no
  second or ongoing cadence has occurred since the 2026-08-10 one-shot fire.
  The 2026-08-12 run was a manual `agentcore invoke`, which does not count.

Cheap way to close all three in one session, if Phase 6 is being run anyway:
during the live pass, fire `agentcore invoke '{}'` twice ~2 s apart (expect
`already_running` on the second, and exactly one `curation_run_complete`),
then enable the schedule for a single day and compare the two consecutive
runs' `card_id` / `created_at` for an already-curated URL. That discharges the
`already_running` gap, the dedup drill, and one real unattended cadence — and
this spec's new per-run metrics make all three trivially checkable afterwards.

## Audit Log

| Date | Auditor | Finding | Severity | Resolution |
|---|---|---|---|---|
| 2026-08-11 | sdd-auditor | **Phases 1–5 conform to contract.md.** All 32 contract items **PASS**; 19 of 22 requirements **PASS**, 2 **PARTIAL by design** (R11/R22 — their remaining halves are Phase-6 steps), 3 **PENDING** (R19–R21, live-only). All 34 offline test rows (T1–T34) verified as real, currently-passing tests inside an auditor-run **144 passed** suite. Independently re-derived, not accepted from `tasks.md`: the offline suite, `cdk synth` (4 stacks, no `cdk.context.json`), `cdk diff` against the **live** account on all three pre-existing stacks (*"Number of stacks with differences: 0"* ⇒ Guarantee 5 holds for real), the synthesized `AiRadarBudget` template read property-by-property, the byte-identity of `src/spike/{pipeline,chat,retrieval,cards,feeds}.py` + `run_spike.py` + `run_chat.py` + `pyproject.toml` + `uv.lock`, and the live pre-state of AWS Budgets / CloudFormation / EventBridge Scheduler. | **INFO** | **APPROVED for the offline scope (Phases 1–5).** No blocking issue. Proceed to Phase 6. |
| 2026-08-11 | sdd-auditor | **O1 — a *non-mapping* `usage` value escapes the degradation guard.** `spike/bedrock.py:119-125` catches `(TypeError, ValueError)` around `int(...)`, but if Bedrock ever returned `usage` as a non-mapping truthy value (a string/list), `usage_block.get(...)` raises `AttributeError`, which propagates out of `summarize_with_usage` and — because the call sits inside `summarize_node`'s per-item `try` — silently converts that item into a `failed` count. The contract's Error-Handling row only pins "no `usage` block (or non-int values)", **both of which are correctly handled**, so this is not a contract violation; but §1's docstring says "missing/**malformed**", which is broader than the code. | **LOW** | Not blocking. One-line hardening on the next touch of this file: widen to `except (AttributeError, TypeError, ValueError)` or guard with `isinstance(usage_block, Mapping)`, and add a 4th param (`usage="junk-string"`) to the existing parametrized T2. **Resolved 2026-08-12: sdd-executor widened `spike/bedrock.py`'s guard to `except (TypeError, ValueError, AttributeError)` (with a comment explaining each case) and added a 4th parametrized case (`usage=["not", "a", "mapping"]`, id `non-mapping-truthy`) to `tests/test_bedrock_usage.py`'s T2. Full suite re-run green at 145 passed (verified by conductor).** |
| 2026-08-11 | sdd-auditor | **O2 — `run_metrics_document` embeds the module-level constants by reference.** `metrics.py:56-57` puts the *same list objects* `EMF_DIMENSIONS` / `METRIC_DEFINITIONS` into the returned dict rather than copies. Harmless today (the document is serialized immediately and nothing mutates it), but a future caller that edits the returned doc in place would mutate module state — including the cardinality guard that Guarantee 8 depends on, which the T11 test would then still pass on the *mutated* value. Contract does not pin copy-vs-reference. | **LOW** | Not blocking. Consider `list(EMF_DIMENSIONS)` / `[dict(m) for m in METRIC_DEFINITIONS]` if `metrics.py` is ever touched again. |
| 2026-08-11 | sdd-auditor | **O3 — intent.md's literal acceptance grep is non-empty, for prose-only reasons.** `grep -rn "boto3\|botocore" src/curation/{nodes,graph,state,summary,metrics}.py` returns **two** lines — `nodes.py:4` and `graph.py:25`, both *comments asserting that boto3 is not imported*. Zero imports exist; the substantive guarantee (Contract Guarantee 4 / R15) holds and is enforced properly by the AST-based T28. This is a wording defect in the criterion (a `grep` for the word cannot distinguish a comment from an import), not an implementation defect, and the `graph.py` comment predates this spec entirely. | **LOW / informational** | No action required. If a future spec restates the criterion, phrase it as "no `import` of …" and cite T28 as the gate, rather than a raw word-grep. |
| 2026-08-11 | sdd-auditor | **O4/O5/O6/O7 — minor items, recorded for completeness.** **(O4)** `TavilyDiscoverer.credits_used()`'s docstring says "the unit PRICE lives in summary.py"; it actually lives in `curation/config.py` (`summary.py` only *reads* it). The implementation copied contract.md §7 verbatim, so this is a defect in the **contract's** prose, faithfully reproduced. **(O5)** `spike/bedrock.py:29-30` has one blank line between `TokenUsage` and `_client = None` (PEP 8 wants two); no linter is configured in `pyproject.toml`, so nothing enforces it either way. **(O6)** The Error-Handling row *"Zero items discovered / zero summarized ⇒ EMF still emitted with `RunsCompleted: 1`"* has no dedicated test; it is true by construction (`RunsCompleted` is the literal `1`) and the zero-state summary is covered by T8, but the EMF-on-an-empty-run assertion itself is absent. **(O7)** `infra/lib/cost_budget.py` omits contract §10's `RemovalPolicy` import — which the pinned body never uses; dropping it is a strict improvement. | **LOW / informational** | None blocking. (O4) fix the sentence in `tavily.py` and contract.md §7 together on the next touch. (O5) cosmetic. (O6) add one `run_metrics_document(zero_summary)["RunsCompleted"] == 1` assertion if `test_run_summary.py` is reopened. (O7) accept as-is. |
| 2026-08-11 | sdd-auditor | **Human-review-driven contract adjustments verified as landed.** (1) `HAIKU_INPUT_USD_PER_1M` / `HAIKU_OUTPUT_USD_PER_1M` are in **`src/spike/config.py:29-32`**, immediately after `HAIKU_MODEL_ID`, read from **bare** env-var names (not `CURATION_*`), with the "Sonnet/Titan prices deliberately absent" rationale; `src/curation/config.py:89-90` carries the matching "the Bedrock prices are NOT here" pointer comment — grep confirms no Bedrock price constant exists in the curation config. (2) `specs/run-observability/tasks.md` § *Follow-ups / Not This Spec* contains both **FU1** (rename/retire `src/spike/`, with the load-bearing-not-dead-code evidence) and **FU2** (full `pydantic-settings` migration of **both** config modules, incl. the `uv add` and architecture-principles-amendment notes), both unchecked and explicitly **not actioned** — and the executor did not action them (`spike/config.py`'s only change is the two constants plus a docstring line that cross-references FU1). | **INFO** | Both confirmed. Nothing to do. |
| 2026-08-12 | sdd-auditor | **Phase 6 executed and independently re-verified — the spec's two "unverifiable offline" risks are both SETTLED, positively.** Roadmap Risk 1 ("CloudWatch never extracts the EMF line — AgentCore does not forward raw stderr as its own event, or wraps it") was the single largest design risk in this spec, with a whole fallback path (`CURATION_EMIT_METRICS=false`, logs-only) held in reserve. It did not materialize. The auditor read the raw log events for run `d577c1c0…` and confirmed the asymmetry directly: the five logger records are each `{"timestamp","level","message":"<escaped JSON string>","logger","requestId","sessionId"}`, whereas the `curation_run_metrics` event's message is `{"_aws": {...}, "event": "curation_run_metrics", …}` **at the top level with nothing around it**. That single observation proves *both* pinned unknowns at once — (1) a raw `sys.stderr` write lands as its **own** log event rather than being merged with a neighbouring line, and (2) it genuinely bypasses the SDK's `RequestContextFormatter`, which is exactly why the contract forbade routing it through `logging`. Downstream: `list-metrics` returns exactly 4 metrics with `"Dimensions": []`, and all four carry one datapoint matching the record. **Task 6.10's fallback was never needed.** | **INFO — risk closed** | The contract's most fragile design decision is vindicated. Preserve the tasks.md note: if anyone ever "tidies" `emit_run_metrics` into a `logger.info(...)` call, the metrics die silently — the offline test `test_emit_run_metrics_never_touches_the_logging_module` is the guard, and it is now known to be guarding something real. |
| 2026-08-12 | sdd-auditor | **F2 — cost estimation is materially better than the contract promised: the Bedrock figure is a measurement, not an estimate.** Roadmap 6.7 / T40 asked only for an order-of-magnitude match, explicitly stating "an exact match is not expected". The auditor queried `AWS/Bedrock`'s own `InputTokenCount`/`OutputTokenCount` for the run window and got `Sum: 10593.0` / `Sum: 2553.0` with `SampleCount: 8.0` on each — **identical** to the `input_tokens`/`output_tokens` `summarize_with_usage` captured, over exactly the 8 expected model calls, with `10593/1e6×$1 + 2553/1e6×$5 = $0.023358` reproducing `estimated_bedrock_cost_usd` exactly. **Delta $0.00.** This validates the whole token-capture seam end to end (Converse `usage` → `TokenUsage` → `summarize_node` accumulation → `RunSummary` → log + EMF) against an independent AWS meter, which no offline test could do. | **INFO — exceeds spec** | None. Worth citing in any future costing spec: Plane A's Bedrock cost line can be trusted as measured, not modelled. |
| 2026-08-12 | sdd-auditor | **F3 — NEW, visible only in live data: the majority of the headline cost figure is the *estimated* half, not the measured half.** For the observed run, `estimated_cost_usd = $0.063358` decomposes into `estimated_bedrock_cost_usd = $0.023358` (**measured**, delta $0.00 vs AWS's meter) and `estimated_tavily_cost_usd = $0.040000` (**estimated** — 5 attempted searches × 1 credit × $0.008, since Tavily's API does not report consumption). So **63% of the headline number is an unvalidated estimate**, and it is the larger component. This is not a defect — Guarantee 10 promised exactly this ("Bedrock figures come from real returned token counts; Tavily figures are attempted searches × credits-per-depth × unit price… labelled *estimated* everywhere"), the direction is conservative, and the price is an env knob (`CURATION_TAVILY_CREDIT_PRICE_USD`). But the ratio was not foreseeable offline and matters for how the `EstimatedCostUsd` metric should be read: it is a **budgeting** signal, not an invoice. | **LOW / informational** | No code change. When the real Tavily plan/rate is known, set `CURATION_TAVILY_CREDIT_PRICE_USD` to it — that one env var moves the majority of the reported figure. Consider splitting `EstimatedCostUsd` into measured/estimated components only if a future spec actually needs to alarm on cost. |
| 2026-08-12 | sdd-auditor | **F4 — live corroboration of the `include_credit=False` decision, from real spend numbers.** The two budgets now report *different* actual spend for the same account and month: the pre-existing "My Monthly Cost Budget" (default cost types, `IncludeCredit: null`) shows `ActualSpend $5.322`, while `ai-radar-monthly-cost` (`IncludeCredit: false`) shows `$5.382` — a $0.06 gap that is precisely the credit-covered charges the default budget nets out. Small today, but it is the mechanism the design feared, observed in the wild: on a credit-covered account the default configuration under-reports gross spend, and would keep under-reporting it right up to the point the credits ran out. The construct docstring's "load-bearing" annotation is correct, and Guarantee 13 is verified against live data rather than only against a synth template. | **INFO** | None. Do not "simplify" `CostTypesProperty` away in a future refactor; this row is the evidence for why it is explicit. |
| 2026-08-12 | sdd-auditor | **F1 — `README.md` and `specs/run-observability/tasks.md` were not updated after the live fire, so both now assert things that are false.** Tasks 6.11 and 6.12 are the documentation half of Phase 6, and 6.11 was not performed. Four `README.md` statements are now **actively wrong**, not merely incomplete: the spec-table row (`:24`) still reads "🔧 Implemented, not yet deployed" and "the real `cdk deploy` + `agentcore deploy` + live-fire verification … has **not** run yet"; "Current live AWS state (**as of 2026-08-10**)" (`:406-415`) still describes two deployed stacks and image `20260810-221147-104`, when there are now **four** stacks and the image is `20260812-162922-638`; "**Status as of this writing:**" (`:485`) repeats the "have **not** run yet" claim; and the test count reads 144 in two places (`:24`, `:498`) when the suite is 145. Separately, **every Phase-6 checkbox in `tasks.md` (6.1–6.12) is still `[ ]`** despite 6.1–6.9 demonstrably having been executed — the auditor re-derived their outcomes from live AWS. This is precisely the failure mode `specs/async-invocation-ack/audit.md` logged as finding **A8** ("documentation residuals … have now flipped from *absent* to *stale*"), recurring one spec later. | **MEDIUM** | Not blocking the code, but it **is** blocking a clean sign-off, because README is the project's stated source of truth for spec status (CLAUDE.md: "that table is the source of truth, not this file"). Fix: perform Task 6.11 (flip the row to "✅ Shipped & live-fire verified" with the real numbers — run `d577c1c0…`, 4 metrics live, budget deployed + subscription confirmed, tokens matching Bedrock exactly; refresh the "Current live AWS state" note to 2026-08-12 / four stacks / the new image; drop the two "not yet run" paragraphs; 144→145), and tick `tasks.md` 6.1–6.9 (6.10 is `N/A — fallback not needed`, 6.11/6.12 on completion). |
| 2026-08-12 | sdd-auditor | **O1 RESOLVED — verified fixed, tested, and in the deployed image.** `src/spike/bedrock.py:123` now reads `except (TypeError, ValueError, AttributeError)` with a comment explaining each case ("`AttributeError`: `usage` itself is some non-mapping truthy value … that has no `.get` at all — `or {}` above only catches the falsy case"). `tests/test_bedrock_usage.py`'s parametrization gained a fourth case, `non-mapping-truthy`, taking the suite 144 → **145 passed**. Deployment check: the file's mtime is `2026-08-12T16:20:16Z`, the CodeBuild image `20260812-162922-638` was pushed `16:29:51Z` — the fix **precedes** the build, so the hardening is in the running image. (Inferred from timestamps, not from reading the image; it is behaviourally inert either way, since the observed run had a well-formed `usage` block on all 8 calls.) | **LOW → RESOLVED** | None. Fixed exactly as recommended, including the regression case. |
| 2026-08-11 | sdd-auditor | **Phase 6 confirmed genuinely not started — recorded so the verdict is not read as broader than it is.** `aws cloudformation describe-stacks` → no `AiRadarBudget`; `aws budgets describe-budgets` → only the pre-existing "My Monthly Cost Budget" ($1/mo, hand-made, untouched — R12's before-state); the deployed agent still runs the `async-invocation-ack` image, so **no production run has ever emitted the new record or the EMF line**; `aws scheduler list-schedules` → the one schedule is still `DISABLED`. Consequences: this spec's Goal 8 ("prove it against real AWS") is **unmet**, Phase 1's Definition-of-done box P6 stays open, and the $500-credit guardrail exists in code but **not in the account**. `tasks.md` correctly leaves Tasks 6.1–6.12 all `[ ]`. | **INFO (expected)** | **SUPERSEDED 2026-08-12** — Phase 6 has since been executed and re-audited; see the four entries above. Retained verbatim for the record. Its statements ("no production run has ever emitted the new record", "the guardrail exists in code but not in the account") were true when written and are now false. |

## Final Verdict (Phases 1–5, offline; 2026-08-11)

> **Superseded — see "Final Verdict (Phase 6 re-audit, 2026-08-12)" at the end
> of this file.** Retained verbatim for the record. Its central reservation
> ("the spec is not done until Phase 6 runs") has since been discharged; its
> `O1` warning has been fixed.

**Status**: **APPROVED WITH RESERVATIONS** — approved *for the offline scope of
this spec* (roadmap Phases 1–5). Phase 6 (real deploy + live fire) is
**unexecuted, by design**, and is explicitly **not** approved-by-proxy here.

**Summary**: The implementation matches contract.md item-for-item — all 32
contract items pass, all 34 offline test rows are real and green inside an
auditor-run 144-test suite, and the three hardest-to-get-right constraints hold
under independent verification: the `curation_run_complete` record is a true
superset (originals asserted by value, not just by presence), the portability
rule survives with zero AWS imports across five modules, and `cdk diff` against
the **live** account shows no change to any pre-existing stack, proving the
execution role gains no permission. The reservations are entirely about what
has not yet been *proven against real AWS*, plus four cosmetic/low items — none
of which blocks the deploy.

**Critical Issues** (must fix before merge): **none.**

**Warnings** (should fix, not blocking):
- **The spec is not done until Phase 6 runs.** R19/R20/R21 and T35–T40 are
  PENDING, so the spec's own Goal 8 is unmet and Phase 1's Definition-of-done
  box P6 stays open. Concretely: no `AIRadar/Curation` metric exists, the
  budget is not deployed, the email subscription is unconfirmed (SNS drops
  notifications silently until someone clicks), and the deployed agent still
  runs the pre-spec image — so production currently emits the **old** 8-field
  record. Until then there is **no live spend guardrail** on the $500 credits.
- **The two unverifiable-offline claims remain unverified** (EMF extraction
  from `/aws/bedrock-agentcore/runtimes/*`; a raw stderr write landing as its
  own log event). The mitigation is in place and correct — the line bypasses
  `logging` deliberately, and `CURATION_EMIT_METRICS=false` is a one-env-var
  fallback with the logs as the record of truth — but Phase 6.7 is the only
  thing that can settle it. If it fails, follow Task 6.10; do **not** improvise
  a `runs` table mid-flight.
- **O1** — widen `summarize_with_usage`'s degradation guard to also catch
  `AttributeError` (a non-mapping `usage` currently turns one item into a
  `failed`). Cheap, and it makes the §1 docstring's "malformed" literally true.

**Recommendations** (nice to have):
- **O2**: copy `EMF_DIMENSIONS` / `METRIC_DEFINITIONS` into the returned EMF
  document so a caller cannot mutate the cardinality guard.
- **O4**: fix the "the unit PRICE lives in summary.py" sentence in both
  `tavily.py` and contract.md §7 (it lives in `curation/config.py`).
- **O6**: one extra assertion for the zero-work EMF case (`RunsCompleted: 1`
  on an all-zero summary) — the row exists in the Error-Handling contract but
  has no dedicated test.
- **O3**: when restating the portability gate in a future spec, phrase it as
  "no `import` of boto3/botocore/bedrock_agentcore" and cite T28; the current
  raw-word grep is tripped by the very comments that document the rule.
- **Phase-1 close-out**: fold the three carried-forward gaps into the Phase 6
  live session — two `agentcore invoke '{}'` calls ~2 s apart (closes
  `already_running`), and one enabled day with a `card_id`/`created_at`
  comparison across the two runs (closes the double-fire dedup drill **and**
  gives Phase 1 its first genuine unattended cadence). All three are cheap
  precisely because this spec's per-run records make them observable.

## Final Verdict (Phase 6 re-audit, 2026-08-12)

> Authored by **sdd-auditor**, 2026-08-12, after Phase 6 was **actually
> executed against real AWS**. Every claim below was re-derived from the live
> account by the auditor — `aws budgets describe-budgets` /
> `describe-notifications-for-budget`, `aws cloudformation describe-stacks`,
> `aws sns list-subscriptions-by-topic` / `get-topic-attributes`,
> `aws cloudwatch list-metrics` / `get-metric-statistics` (both
> `AIRadar/Curation` and `AWS/Bedrock`), `aws logs filter-log-events` +
> `start-query`/`get-query-results`, `aws dynamodb scan`,
> `aws ecr describe-images`, `agentcore status`, `aws scheduler
> list-schedules`, and a fresh `uv run pytest tests/` — **not** accepted from
> the executor's Phase 6 report.

**Status**: **APPROVED WITH RESERVATIONS**

The *engineering* is done and proven: **APPROVED unconditionally on code,
contract conformance, and live behaviour.** All 22 requirements now PASS
(R19–R21 flipped from PENDING; R11 from PARTIAL), all 32 contract items PASS,
all 40 test rows PASS (T1–T34 automated, T35–T40 live-fire), and the single
LOW finding from the first pass (**O1**) has been fixed with a regression test.
The one reservation is **documentation, not code** — and it is a real one, so
the verdict is not upgraded to a clean APPROVED yet.

**Summary**: Phase 6 did not merely pass; it settled the spec's two genuinely
unknowable-offline questions in the *favourable* direction and produced a
better result than the roadmap asked for. CloudWatch **does** extract EMF from
the AgentCore runtime log group, and the raw stderr write **does** land as its
own top-level log event rather than being wrapped by the SDK formatter — the
auditor confirmed this by reading the raw events and observing that the five
logger records carry a `{"timestamp","level","message":"…"}` envelope while the
EMF record does not. The reserved fallback (`CURATION_EMIT_METRICS=false`,
logs-only) was never needed. The budget deployed cleanly with the topic-policy
dependency intact, the email subscription is genuinely **confirmed** (the one
step no automation can perform, and the spec's most likely silent failure),
and the cost figures beat their own acceptance bar: Bedrock's own meter reports
`10593` input / `2553` output tokens over 8 calls for the run — **identical**
to what the pipeline captured, delta **$0.00**, against a criterion that only
demanded an order of magnitude.

**Critical Issues** (must fix before merge): **none.**

**Warnings** (should fix, not blocking the code):
- **F1 — `README.md` and `tasks.md` are stale to the point of being false.**
  Task 6.11 was not performed and Task 6.12's checkbox work is unticked, so the
  README still advertises this spec as "🔧 Implemented, not yet deployed" with
  "the real `cdk deploy` + `agentcore deploy` + live-fire verification has
  **not** run yet", and still describes the live AWS state as of 2026-08-10
  (two stacks, old image) when there are now four stacks and a new image; the
  test count is 144 in two places, now 145. Meanwhile every Phase-6 checkbox in
  `tasks.md` sits at `[ ]` despite 6.1–6.9 having demonstrably run. Per
  CLAUDE.md, that README table **is** the project's source of truth for spec
  status, so leaving it wrong is worse than leaving it empty — and it is the
  same failure `async-invocation-ack` logged as finding A8 one spec ago. This
  is the sole reason the verdict retains "WITH RESERVATIONS"; it is ~20 minutes
  of editing and requires no code change.

**Recommendations** (nice to have):
- **F3**: be aware that ~63% of the headline `estimated_cost_usd` for a typical
  run is the *Tavily estimate*, not the measured Bedrock cost. Set
  `CURATION_TAVILY_CREDIT_PRICE_USD` to the real plan rate once known — that
  one env var moves the majority of the number. Treat the `EstimatedCostUsd`
  metric as a budgeting signal, not an invoice.
- **O2 / O4 / O6** (unchanged from the first pass, all LOW): copy the EMF
  constant lists into the returned document; fix the "the unit PRICE lives in
  summary.py" sentence in `tavily.py` **and** contract.md §7; add the zero-work
  `RunsCompleted: 1` assertion.
- **Phase-1 close-out — 6 of 8 boxes PASS, P3 and P5 remain PARTIAL.** P6, the
  box this spec exists to close and the only one still unchecked when it began,
  is now **closed with live evidence**. The two survivors are inherited
  operational-verification gaps from Spec 05, untouched by a single manual
  invoke: the **double-fire dedup drill** has still never been run, and
  **`already_running`** has still never been observed in production; the
  schedule remains **`DISABLED`**, so **no unattended daily cadence has ever
  elapsed**. Do not let the successful manual invoke be read as closing P5 —
  it exercises the runtime path, not the unattended one. All three close cheaply
  in one future session: two `agentcore invoke '{}'` calls ~2 s apart (expect
  `already_running` on the second and exactly one `curation_run_complete`),
  then one enabled day with a `card_id`/`created_at` comparison across the two
  consecutive scheduled runs. This spec's now-live per-run metrics make all
  three trivially observable — `RunsCompleted` alone answers "did it run
  unattended today?", which is precisely the question Phase 1 could not answer
  before.

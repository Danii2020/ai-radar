# Tasks: run-observability

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

Phases map 1:1 to `roadmap.md`. Every task cites the contract item(s) it
implements; do not invent surface that contract.md does not pin.

## Phase 1: Pure foundation (config, RunSummary, cost math, EMF document)

- [x] Task 1.1a: Add the two Bedrock unit prices immediately after
      `HAIKU_MODEL_ID` — `HAIKU_INPUT_USD_PER_1M` / `HAIKU_OUTPUT_USD_PER_1M`,
      env vars of the same bare names (that file's convention, NOT
      `CURATION_*`), with the comment saying they sit beside the model ID they
      price and that Sonnet/Titan prices are deliberately absent; optionally
      note in the module docstring that this file holds shared cross-plane
      AWS/Bedrock config — `src/spike/config.py` (contract §4a)
- [x] Task 1.1b: Add the "Run observability (Spec 06)" block —
      `TAVILY_SOURCE_PREFIX`, `TAVILY_CREDIT_PRICE_USD`,
      `TAVILY_CREDITS_BY_DEPTH`, `TAVILY_DEFAULT_CREDITS_PER_SEARCH`,
      `METRIC_NAMESPACE`, `EMIT_RUN_METRICS` — with the "this is an estimate,
      not a meter" comment on the Tavily block and a pointer comment that the
      Bedrock prices live in `spike/config.py` —
      `src/curation/config.py` (contract §4b)
- [x] Task 1.2: Create the `RunSummary` frozen dataclass with the pinned field
      set **and order**, plus `to_dict()` — `src/curation/summary.py` (C4)
- [x] Task 1.3: Implement `split_by_origin` (prefix-based, no `curation.tavily`
      import) — `src/curation/summary.py` (C5)
- [x] Task 1.4: Implement `estimate_bedrock_cost_usd` (prices from
      `spike_config.HAIKU_*_USD_PER_1M`) / `estimate_tavily_cost_usd` (price
      from `config.TAVILY_CREDIT_PRICE_USD`) — `summary.py` imports BOTH
      config modules (`from spike import config as spike_config` +
      `from . import config`) and reads every price via the module object
      (never `from ... import X`), round to 6 dp — `src/curation/summary.py`
      (C6)
- [x] Task 1.5: Implement `build_run_summary(**kwargs)` — defensive `state`
      reads, `cards_written = max(persisted - store_failures, 0)`, cost
      derivation, `duration_s` rounded to 1 dp — `src/curation/summary.py`
      (C7/C8)
- [x] Task 1.6: Create `src/curation/metrics.py` with `METRIC_DEFINITIONS`
      (exactly 4), `EMF_DIMENSIONS = [[]]`, `EVENT_NAME`, and the comment
      forbidding per-run dimensions — `src/curation/metrics.py` (C11)
- [x] Task 1.7: Implement `run_metrics_document(summary, timestamp_ms=None)`
      producing the pinned EMF shape (summary payload first, then the four
      PascalCase metric targets) — `src/curation/metrics.py` (C9)
- [x] Task 1.8: Implement `emit_run_metrics(summary, stream=None,
      timestamp_ms=None)` — kill-switch aware, `sys.stderr` resolved at call
      time, one `json.dumps(...) + "\n"` write, flush, returns `bool`, never
      uses `logging` — `src/curation/metrics.py` (C10)
- [x] Task 1.9: Portability check —
      `grep -n "boto3\|botocore\|bedrock_agentcore" src/curation/summary.py
      src/curation/metrics.py` returns nothing (R15)

## Phase 2: Token capture at the Bedrock seam

- [x] Task 2.1: Add the frozen `TokenUsage` dataclass (`input_tokens`,
      `output_tokens`, both defaulting to 0) — `src/spike/bedrock.py` (C1)
- [x] Task 2.2: Add `summarize_with_usage(item) -> tuple[dict, TokenUsage]` —
      the existing Converse call body, reading `resp.get("usage", {})`
      defensively; unchanged `RuntimeError` when no `toolUse` block —
      `src/spike/bedrock.py` (C1/C3)
- [x] Task 2.3: Reduce `summarize(item) -> dict` to
      `return summarize_with_usage(item)[0]`, docstring noting it is preserved
      verbatim for `spike.pipeline` (Phase 0) and Plane B —
      `src/spike/bedrock.py` (C2/R4)
- [x] Task 2.4: Confirm `git diff src/spike/` touches **only** `bedrock.py`
      and `config.py` (the latter from Task 1.1a) — `pipeline.py`, `chat.py`,
      `retrieval.py`, `cards.py`, `feeds.py` untouched (R4)

## Phase 3: Instrument the graph (state, nodes, discoverer accessors)

- [x] Task 3.1: Extend `CurationState` with `run_id`, `discovered_by_source`,
      `persisted`, `input_tokens`, `output_tokens`; update the section comment
      to "consumed by Spec 06" — `src/curation/state.py` (C12)
- [x] Task 3.2: Add `logger = logging.getLogger(__name__)` and the
      `_log(event, state, **fields)` helper (JSON, always includes `run_id`) —
      `src/curation/nodes.py` (C13–C16)
- [x] Task 3.3: `discover_node` — group `raw` by `RawItem.source` into
      `discovered_by_source`, return it, emit `discover_complete` —
      `src/curation/nodes.py` (C13)
- [x] Task 3.4: `summarize_node` — call `summarize_with_usage`, accumulate
      tokens INSIDE the existing per-item `try` right after the call; convert
      the failure `print` to a `summarize_item_failed` WARNING with `url` +
      `error`; emit `summarize_complete`; return the two token counters —
      `src/curation/nodes.py` (C14/C15)
- [x] Task 3.5: `persist_node` — return `{"persisted": len(cards)}` and emit
      `persist_complete`; leave `dedup_node` / `rank_node` untouched and
      silent — `src/curation/nodes.py` (C16)
- [x] Task 3.6: `TavilyDiscoverer` — reset + increment `self._searches` per
      seed attempt (including failures), add `searches()` and
      `credits_used()` (depth map + 1-credit fallback) —
      `src/curation/tavily.py` (C17)
- [x] Task 3.7: `TavilyDiscoverer.discover()` — build the source label from
      `config.TAVILY_SOURCE_PREFIX`; verify the emitted string is
      byte-identical to `"Tavily: {topic}"` — `src/curation/tavily.py` (C19)
- [x] Task 3.8: `CompositeDiscoverer` — duck-typed `searches()` /
      `credits_used()` sums defaulting to 0; no new import —
      `src/curation/composite.py` (C18)
- [x] Task 3.9: Portability check across `src/curation/nodes.py`,
      `src/curation/graph.py`, `src/curation/state.py`,
      `src/curation/composite.py` (R15)

## Phase 4: Composition roots + offline tests + docs

- [x] Task 4.1: Add `_configure_curation_logging()` (attach the
      `bedrock_agentcore.app` logger's handlers to `logging.getLogger
      ("curation")`, INFO, called once at import) — `runtime_app.py` (C20)
- [x] Task 4.2: Change `_run_curation_pipeline()` →
      `_run_curation_pipeline(run_id: str) -> RunSummary`: time itself, pass
      `{"max_items": config.MAX_ITEMS, "run_id": run_id}` into the UNCHANGED
      compiled graph, gather `discoverer.searches()/credits_used()/failures()`
      and `store.failures()`, return `build_run_summary(...)` —
      `runtime_app.py` (C21)
- [x] Task 4.3: Update `_curation_run`: `asyncio.to_thread
      (_run_curation_pipeline, run_id)`; log `{"event":
      "curation_run_complete", **summary.to_dict()}`; then
      `emit_run_metrics(summary)` inside its OWN try/except logging
      `curation_metrics_failed` at WARNING; failure path unchanged —
      `runtime_app.py` (C22/C23)
- [x] Task 4.4: `run_curation.py` — `logging.basicConfig(level=INFO,
      format="%(message)s")`, generate `run_id = uuid.uuid4().hex`, pass it
      into `invoke`, build the same summary via `build_run_summary`, print
      counts + tokens + Tavily credits + estimated cost; do **not** call
      `emit_run_metrics` — `run_curation.py` (C24)
- [x] Task 4.5: Update `summarize_stub_factory` to return
      `(model_out, TokenUsage(...))` with a per-item token knob, keeping every
      existing behavior (relevance map, `raise_for_urls`) — `tests/conftest.py`
- [x] Task 4.6: Repoint the monkeypatch target from `nodes.summarize` to
      `nodes.summarize_with_usage` **without weakening any existing
      assertion** — `tests/test_graph.py`, `tests/test_composite.py`,
      `tests/test_dynamo_store.py`
- [x] Task 4.7: Update `tests/test_runtime_app.py` T8 (superset record: the
      eight originals keep their exact values) and T12 (`RunSummary` return,
      `run_id` in the graph input) — `tests/test_runtime_app.py` (T22/T23)
- [x] Task 4.8: `.env.example` — document the five new knobs under the
      section matching each one's home module: `HAIKU_INPUT_USD_PER_1M` /
      `HAIKU_OUTPUT_USD_PER_1M` beside the existing `HAIKU_MODEL_ID` line
      (spike/Bedrock block), and `CURATION_TAVILY_CREDIT_PRICE_USD`,
      `CURATION_METRIC_NAMESPACE`, `CURATION_EMIT_METRICS` in the curation
      block — `.env.example` (R22)
- [x] Task 4.9: `README.md` — spec-table row (`run-observability`), a "Run
      observability" section (the 4 metrics + their monthly cost, both pinned
      Logs Insights queries, the "records are nested under `message` except
      the EMF line" note), and the budget deploy/confirm/teardown runbook —
      `README.md` (R22)
- [x] Task 4.10: Confirm no dependency drift: `uv sync` leaves `uv.lock`
      unchanged and `pyproject.toml` untouched (R17)
- [x] Task 4.11: Write `tests/test_bedrock_usage.py` (T1–T3) — usage
      extraction, missing-`usage` degradation, `summarize()` back-compat,
      against a fake Bedrock client — `tests/test_bedrock_usage.py`
- [x] Task 4.12: Write `tests/test_run_summary.py` (T4–T13) — cost math,
      `split_by_origin`, identities, `to_dict()` order, EMF document shape,
      cardinality guard, kill switch, one-raw-JSON-line via `io.StringIO` —
      `tests/test_run_summary.py`
- [x] Task 4.13: Add the new graph-level assertions (T14–T18) and the
      portability guard (T28) — `tests/test_graph.py`
- [x] Task 4.14: Add `searches()` / `credits_used()` / source-label tests
      (T19–T21) — `tests/test_tavily.py`, `tests/test_composite.py`
- [x] Task 4.15: Add the runtime-app metric tests (T24–T27) —
      `tests/test_runtime_app.py`

## Phase 5: Budget infrastructure (CDK) + synth tests

- [x] Task 5.1: Create the `CostBudget` construct — SNS topic (`enforce_ssl`)
      + `EmailSubscription` + the `budgets.amazonaws.com` publish policy with
      `aws:SourceAccount`/`aws:SourceArn` conditions —
      `infra/lib/cost_budget.py` (C27/C29)
- [x] Task 5.2: Add the `CfnBudget` (`COST`/`MONTHLY`, `ai-radar-monthly-cost`,
      $250 limit, `include_credit=False` + the full explicit `CostTypes`) and
      the three ABSOLUTE_VALUE/ACTUAL/GREATER_THAN notifications at 50/100/250
      with the topic as SNS subscriber — `infra/lib/cost_budget.py` (C25/C26)
- [x] Task 5.3: Add `self.budget.node.add_dependency(policy_result.
      policy_dependable)` with the comment explaining the CreateBudget/SNS
      validation race — `infra/lib/cost_budget.py` (C28)
- [x] Task 5.4: Create `CostBudgetStack` with the four context overrides
      (`budget_name`, `budget_email`, `budget_limit_usd`,
      `budget_thresholds_usd` as a comma string) and the five `CfnOutput`s —
      `infra/stacks/cost_budget_stack.py` (C30)
- [x] Task 5.5: Wire `CostBudgetStack(app, "AiRadarBudget")` into the CDK app
      without touching the other three stacks — `infra/app.py` (C31)
- [x] Task 5.6: Write the synth-only budget tests (T29–T34), mirroring
      `tests/test_infra_curation_schedule.py`'s helper style and its
      `sys.path.insert(..., "infra")` convention —
      `tests/test_infra_cost_budget.py`
- [x] Task 5.7: `uv run --group infra cdk synth --app "python infra/app.py"
      AiRadarBudget` with **no AWS credentials** — must succeed and write no
      `cdk.context.json`
- [x] Task 5.8: `uv run pytest tests/ -v` — whole suite green and offline;
      `git status` shows no new `cdk.context.json` (R18)

## Phase 6: Live deploy + verification (manual runbook — real AWS, real money)

> Manual steps, never automated tests. These twelve tasks expand roadmap.md
> Phase 6's ten steps (6.1↔1, 6.2–6.3↔2, 6.4↔3, 6.5↔4, 6.6–6.7↔5, 6.8↔6,
> 6.9↔7, 6.10↔8, 6.11↔9, 6.12↔10). Record every result in `audit.md`.

- [x] Task 6.1: Pre-flight — `agentcore status`, baseline
      `aws dynamodb scan --table-name ai-radar-cards --select COUNT`, and
      `aws budgets describe-budgets --account-id 536697225154` to record the
      pre-existing "My Monthly Cost Budget" **before** touching anything (R12)
      — done 2026-08-11/12; pre-state recorded in audit.md (only "My Monthly
      Cost Budget" existed; `ai-radar-cards` baseline 72).
- [x] Task 6.2: `uv run --group infra cdk deploy --app "python infra/app.py"
      AiRadarBudget`; confirm `cdk diff` on `AiRadarCardStore`,
      `AiRadarRuntimeRole`, `AiRadarSchedule` is empty (R16)
      — done 2026-08-12; `AiRadarBudget` `CREATE_COMPLETE` in ~15s, `cdk diff`
      on the three pre-existing stacks: no differences.
- [x] Task 6.3: Verify the deployed budget: `aws budgets describe-budget`
      (COST/MONTHLY/`IncludeCredit: false`) + `describe-notifications-for-
      budget` (three ACTUAL thresholds), and that the pre-existing budget is
      unchanged (R10/R12/T35)
      — done 2026-08-12; verified live, see audit.md T35 (three notifications
      at 50/100/250, all `OK`; pre-existing budget still `$1.0`, untouched).
- [x] Task 6.4: Click the SNS confirmation email; verify with
      `aws sns list-subscriptions-by-topic` (no `PendingConfirmation`), then
      `aws sns publish` a test message and confirm it arrives (R11/T36)
      — done 2026-08-12; real ARN (not `PendingConfirmation`), test message
      delivered and received by the human. See audit.md T36.
- [x] Task 6.5: `agentcore deploy` (rebuild the image — the instrumentation is
      inert until then); confirm the new ECR tag is live
      — done 2026-08-12; new tag `20260812-162922-638` pushed, superseding
      `20260810-221147-104`; `agentcore status` → Ready.
- [x] Task 6.6: `agentcore invoke '{}'`; ~60 s later collect the
      `curation_run_complete` record for that `run_id` and verify the eight
      original fields plus non-zero `input_tokens`, the RSS/Tavily split
      identity, and `estimated_cost_usd > 0` (R20/T38)
      — done 2026-08-12; `run_id d577c1c0c1a240edabb5b6d461a15c07`, all eight
      original fields present with correct values plus new fields
      (`input_tokens=10593`, `discovered_rss=30`+`discovered_tavily=20`=50,
      `estimated_cost_usd=0.063358`). See audit.md T38.
- [x] Task 6.7: Verify the `curation_run_metrics` line appears as its **own**
      top-level-JSON log event (not nested under `message`), then
      `aws cloudwatch list-metrics --namespace AIRadar/Curation` → 4 metrics
      and a `get-metric-statistics` datapoint for `EstimatedCostUsd`
      (R8/R20/T37)
      — done 2026-08-12; confirmed the EMF line has no `{"message": "..."}`
      wrapper (unlike the other 5 records); `list-metrics` → exactly 4
      metrics, `Dimensions: []`, `EstimatedCostUsd` datapoint = 0.063358,
      matching the log record exactly. See audit.md T37/T38.
- [x] Task 6.8: Run both pinned Logs Insights queries; confirm "failed counts
      for the last 7 runs" is genuinely answerable (R21/T39)
      — done 2026-08-12; both queries returned `recordsMatched: 1`,
      `status: Complete`. See audit.md T39.
- [x] Task 6.9: Sanity-check `estimated_bedrock_cost_usd` against Bedrock's
      own reported usage / Cost Explorer for the day; record the delta (T40)
      — done 2026-08-12; `AWS/Bedrock` `InputTokenCount`/`OutputTokenCount`
      reported 10593/2553, an **exact** match to the pipeline's own capture
      (delta $0.00), far exceeding the order-of-magnitude bar. See audit.md
      T40.
- [ ] Task 6.10: If EMF metrics do **not** appear: set
      `CURATION_EMIT_METRICS=false` (via `agentcore configure --env`), record
      the negative result as an audit finding, and keep logs as the record of
      truth — do **not** improvise a `runs` table mid-flight (roadmap Risk 1)
      — **N/A, left unchecked deliberately**: metrics appeared correctly on
      the first real run, so this fallback path was never exercised. Not a
      gap — there was simply nothing to trigger it.
- [x] Task 6.11: Update `README.md` with the verified numbers, the "current
      live AWS state" note (now four stacks), and the
      `cdk destroy AiRadarBudget` teardown line; tick the Phase 1
      Definition-of-done box P6 (R22)
      — done 2026-08-12 (sdd-documentarian pass): spec-table row, "Current
      live AWS state", "Run observability" section, and test count (144→145)
      all refreshed with the real verified numbers; closes audit.md finding
      F1. The `cdk destroy AiRadarBudget` teardown line was already present
      from Task 4.9. (Phase 1 Definition-of-done box P6 lives in
      `tasks/phase-1-curation-mvp/README.md`, outside this spec's file set —
      not edited here.)
- [ ] Task 6.12: Fill in `specs/run-observability/audit.md` — Test Coverage
      T35–T40, the Audit Log entries, and the **Phase 1 close-out table**
      (P1–P8 plus the carried-forward unverified claims) (roadmap Phase 6.10)
      — auditor's own task; not touched here per scope.

## Blocked Items

[None yet]

## Follow-ups / Not This Spec

Tracked here so they are not lost, and explicitly **not actioned** by this
spec's executor.

- [x] **FU1 — Rename/retire the `src/spike/` package (housekeeping, future
      spec).** The directory name is a Phase-0 holdover and now actively
      misleads: despite the name, almost everything in it is **live production
      code**, not a spike.
      - `spike.bedrock`, `spike.cards`, `spike.feeds`, `spike.config` are
        imported directly by Plane A (`curation.nodes`, `curation.local`,
        `curation.dynamo`, `curation.tavily`, `curation.summary`,
        `runtime_app.py`, `run_curation.py`) and run in the deployed
        AgentCore image today.
      - `spike.chat` and `spike.retrieval` **are** Plane B — there is no
        replacement module; `run_chat.py` is the only entrypoint they have.
      - Only `spike.pipeline` is genuinely superseded (by
        `curation/graph.py`); its sole caller is the legacy `run_spike.py`.
      A rename (e.g. `spike/` → `shared/`, and/or splitting the Plane-B-only
      pieces into their own package) would improve clarity, but it touches
      ~10 files across **both** planes, changes every import path and test
      patch target, and delivers **zero functional change** — which is exactly
      the kind of churn this spec's "additive only, extend the existing seams"
      framing forbids. It also interacts with
      `docs/architecture-principles.md` §2's future monorepo layout
      (`apps/curation`, `apps/api`, `apps/web`, `packages/contracts`), so it
      is better done once, deliberately, as part of that move than piecemeal
      now. **Do not bundle it into `run-observability`.**
      *(Context: raised while reviewing contract.md §1 — "why does this build
      on `spike/bedrock.py` if `spike` was just the Phase 0 spike?" Answer:
      because it is load-bearing, not dead code.)*

- [ ] **FU2 — Migrate config loading to `pydantic-settings` (own spec, after
      `run-observability` ships).** Confirmed decision: a **full** migration of
      **both** `src/spike/config.py` and `src/curation/config.py` to
      `BaseSettings` — deliberately *not* a partial adoption covering only this
      spec's new observability constants, which would leave two config styles
      side by side and make the codebase less consistent, not more.
      Rationale to carry into that spec:
      - **Validation at startup.** Today a bad override (e.g.
        `HAIKU_INPUT_USD_PER_1M=abc` or `CURATION_TAVILY_CREDIT_PRICE_USD=`)
        either explodes at import with a bare `ValueError` or surfaces
        confusingly deep inside cost math; `BaseSettings` turns that into one
        clear, typed, load-time error naming the offending field.
      - **Consistent `.env` loading**, replacing the current per-module
        `load_dotenv()` + `os.getenv` + hand-rolled coercions
        (`str(raw).lower() == "true"`, `_csv()`, `float(...)`, the `";"`-split
        seed list).
      - It is the *full* fix for "improve how config settings are loaded",
        which is why it earns its own spec rather than riding along here.
      **Dependency note:** `pydantic-settings` is currently only a
      **transitive** dependency (via `bedrock-agentcore` /
      `bedrock-agentcore-starter-toolkit`), never a chosen one — adopting it
      means adding it explicitly to `pyproject.toml` (`uv add`) rather than
      relying on someone else's transitive pin.
      **Principles note:** that spec must also revisit
      `docs/architecture-principles.md`'s 2026-07 deferral of Pydantic. That
      deferral was framed around the **`Card` domain contract** ("promote it to
      a versioned, validated schema when the frontend or a real API exists"),
      so its architect should judge whether env-var settings loading is a
      different-enough concern to fall outside it — and either way, amend the
      principles doc explicitly so the next reader is not left guessing.
      **Not this spec:** `run-observability`'s config additions stay plain
      `os.getenv`, per contract.md's "no new dependency" guarantee.

## Notes

- **Do not re-litigate the persistence decision.** Metrics (EMF) + structured
  logs, *not* a DynamoDB `runs` table — the reasoning is in intent.md Goal 5
  and was an explicit architect decision delegated by the source brief.
- **The `curation_run_complete` record is append-only.** Adding fields is
  fine; renaming, retyping, or dropping any of the original eight is a
  breaking change to `README.md`, `tests/test_runtime_app.py`, and
  `specs/async-invocation-ack/audit.md`.
- **EMF is fragile by construction**: the log event must be the JSON document
  and nothing else. Anything routed through `logging` gets wrapped by the
  SDK's `RequestContextFormatter` and stops being EMF. If a future change
  "tidies" `emit_run_metrics` into a logger call, it silently kills the
  metrics.
- **Never add a dimension** to the EMF document. `run_id` as a dimension would
  create one billable custom metric per run.
- **Two config files is deliberate, not an oversight.** Bedrock unit prices
  live in `spike/config.py` (with `HAIKU_MODEL_ID`, the model they price);
  curation-plane knobs live in `curation/config.py`. No `pydantic-settings`:
  `docs/architecture-principles.md` defers Pydantic until `Card` becomes a
  versioned API contract, and the package is only present transitively via
  `bedrock-agentcore` / the starter toolkit.
- **Portability grep is a real acceptance gate**, not a style preference:
  `src/curation/{nodes,graph,state,summary,metrics}.py` must stay free of AWS
  SDK imports so the graph still lifts off AgentCore unchanged.
- **The auditor has a second job** (roadmap Phase 6.10 / audit.md's close-out
  table): this is the last Phase 1 spec, so its audit also checks the whole
  phase against the *Definition of done* and lists what Phase 1 claimed but
  never verified.
- Live steps cost real money but very little: one bounded curation run
  (~$0.01, `SPIKE_MAX_ITEMS`-capped), AWS Budgets (first two budgets free),
  SNS (free tier), and ~$1.20/month of custom metrics thereafter.

## Executor Completion Log

**2026-08-11 — Phases 1-5 complete (sdd-executor).**

- All Phase 1-5 tasks above are checked off and implemented per contract.md.
- One deviation, explicitly authorized by this file's own Task 4.6 ("Repoint
  the monkeypatch target from `nodes.summarize` to `nodes.summarize_with_usage`
  ... `tests/test_graph.py`"): `test_dedup_runs_before_cap_never_summarizes_seen_items`
  in `tests/test_graph.py` still patched `nodes_module.summarize` (a stale
  target Task 4.6's own churn sweep should have caught but missed — every
  other occurrence in that file was already repointed). Left as-is it would
  have called the REAL `summarize_with_usage` during a supposedly 100%-offline
  test. Fixed by repointing that one `monkeypatch.setattr` call to
  `summarize_with_usage` and updating the local stub's return shape to
  `(dict, TokenUsage(0, 0))` — no assertion in the test was changed or
  weakened.
- Full suite: `uv run pytest tests/` — **144 passed**, fully green, no
  `--continue-on-collection-errors` needed.
- `uv run --group infra cdk synth --app "python infra/app.py"` — succeeds for
  all four stacks (`AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarSchedule`,
  `AiRadarBudget`), no `cdk.context.json` written.
- `uv run --group infra cdk diff --app "python infra/app.py" AiRadarCardStore
  AiRadarRuntimeRole AiRadarSchedule` — **all three: "There were no
  differences."** Confirms Guarantee 5 / Success Criteria (execution role
  gains no new permission).
- `uv run run_curation.py` — ran live against real Bedrock/Tavily/DynamoDB;
  printed the new richer summary line (rss/tavily split, tokens, tavily
  searches/credits, estimated cost) and the three node JSON records.
- `uv sync` / `uv.lock` / `pyproject.toml` — untouched (`git diff` empty).
- Phase 6 (real `cdk deploy` + `agentcore deploy` + live-fire) intentionally
  **not started** — out of this executor pass's scope per the conductor's
  instructions; left for the human + a follow-up pass.

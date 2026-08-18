# AI Radar

AI-news curation feed + RAG chatbot. See [`docs/app-design-on-agentcore.md`](docs/app-design-on-agentcore.md) for the full design.

## Phase 1 — Curation MVP (all 6 specs shipped)

Refactors the Phase 0 loop into a **LangGraph `StateGraph`** with infra injected
behind Protocols, so discovery and persistence can be swapped without touching
graph/node code. See [`tasks/phase-1-curation-mvp/`](tasks/phase-1-curation-mvp/)
for the full build plan and [`specs/`](specs/) for each shipped spec's contract.

```
discover (RSS + Tavily, composite, deduped)  →  dedup  →  summarize + tag  →  rank  →  persist
```

| Spec | Status | What it added |
|---|---|---|
| [`curation-graph`](specs/curation-graph/) | ✅ Shipped | The `StateGraph` itself (`src/curation/graph.py`), the `Discoverer`/`CardStore` Protocols (`interfaces.py`), and the local JSON-file defaults (`local.py`) — reproduces Phase 0 behavior exactly. |
| [`tavily-discovery`](specs/tavily-discovery/) | ✅ Shipped | `TavilyDiscoverer` (web search) + `CompositeDiscoverer` (RSS + Tavily, cross-source deduped) behind the same `Discoverer` Protocol — no graph/node changes. |
| [`dynamodb-card-store`](specs/dynamodb-card-store/) | ✅ Shipped | `DynamoCardStore` (DynamoDB persistence + dedup) + a CDK construct (`infra/`) provisioning the table and a feed-read GSI (designed now for Phase 2) — same `CardStore` Protocol, opt-in via `CARD_STORE_BACKEND=dynamo`. |
| [`runtime-packaging`](specs/runtime-packaging/) | ✅ Shipped & deploy-verified | Wraps the unchanged graph in a `BedrockAgentCoreApp` entrypoint (`runtime_app.py`), a least-privilege execution-role + Tavily-secret CDK stack (`infra/lib/agent_runtime.py`), and a `uv`-based Dockerfile. Deployed for real on 2026-07-28 (real Tavily key, cards landed in `ai-radar-cards`, teardown verified clean) — see the runbook below. Redeployed 2026-08-10 to support the `eventbridge-schedule` live fire and **currently still up** (not torn down) — see "Current live AWS state" below. |
| [`eventbridge-schedule`](specs/eventbridge-schedule/) | ✅ Shipped & live-fire verified | Daily `EventBridge Scheduler` schedule (`infra/lib/curation_schedule.py` → `AiRadarSchedule` stack) invoking the deployed Runtime agent via the `Universal` target — SQS dead-letter queue, 15-min flexible window, 3 retries, 2h max event age. Deploys `DISABLED` by default. Real-deployed and live-fired for real on 2026-08-10. **That first live fire hit a real bug** (Scheduler's ~30s synchronous target timeout caused a double-run, finding F5) — fixed and re-verified by `async-invocation-ack` below. |
| [`async-invocation-ack`](specs/async-invocation-ack/) | ✅ Shipped & live-fire verified | Fixes `eventbridge-schedule` finding F5. `runtime_app.py`'s entrypoint is now `async def handler`, acking immediately (`{"status": "accepted", "run_id": …}`) and running the **unchanged** curation graph as a background task via the SDK's `add_async_task`/`complete_async_task`; a single-flight guard rejects a second invocation mid-run with `already_running`. No `infra/`, `src/`, or Dockerfile change. Redeployed and live-fire re-tested 2026-08-10: one Scheduler fire → exactly one run (`InvocationAttemptCount=1`, **zero** `TargetErrorCount` datapoints, one `curation_run_complete` record), card count rose cleanly 48→56, DLQ stayed 0. See the runbook below. |
| [`run-observability`](specs/run-observability/) | ✅ Shipped & live-fire verified | A `RunSummary` (`src/curation/summary.py`) per run — discovered rss/tavily split, tokens, Tavily searches/credits, estimated Bedrock+Tavily cost — logged as a strict superset of the existing `curation_run_complete` record and persisted as 4 CloudWatch EMF custom metrics (`src/curation/metrics.py`, namespace `AIRadar/Curation`), plus a new, separate CDK-managed AWS Budget (`AiRadarBudget` stack) at $50/$100/$250 via SNS email. `uv run pytest tests/` is green (145 tests). Real-deployed and live-fire verified 2026-08-12: `AiRadarBudget` stack created (`cdk diff` on the three pre-existing stacks stayed empty — no new IAM permission), the SNS email subscription was confirmed and a real test message delivered, the agent was rebuilt to image `20260812-162922-638`, and a real invoke produced all 4 metrics with datapoints plus an enriched `curation_run_complete` record whose token counts matched Bedrock's own CloudWatch meter exactly (10593 in / 2553 out, delta $0.00) — see "Run observability" below. |

All six planned specs are shipped and deploy/live-fire-verified. Two
operational verification gaps remain open — inherited from `dynamodb-card-store`
/ `eventbridge-schedule`, not new-code gaps — and are unaffected by
`run-observability`: the prescribed double-fire dedup drill has never been run
as its own test, and the daily schedule has never run **unattended** (it stays
`DISABLED`; every fire to date has been a manual one-shot). See
[`specs/run-observability/audit.md`](specs/run-observability/audit.md)'s
Phase 1 close-out table for the full per-box evidence.

### Cross-cutting specs (post-Phase-1)

| Spec | Status | What it added |
|---|---|---|
| [`pydantic-settings-config`](specs/pydantic-settings-config/) | ✅ Shipped | Both config modules (`src/shared/config.py`, `src/curation/config.py`) now load through `pydantic-settings` instead of hand-rolled `os.getenv`/`_csv()` parsing. Zero env-var renames, zero default changes, zero consumer-file edits — a loading-mechanism swap only. `uv run pytest tests/` is green (261 tests, incl. 116 new in `tests/test_config.py`, the first-ever coverage of either config module). Local-only; no redeploy, no infra change, $0 AWS spend. |

> Also see [`specs/rename-spike-to-shared/`](specs/rename-spike-to-shared/)
> (`src/spike` → `src/shared`, `SPIKE_*` → `AI_RADAR_*`), the other
> zero-behavior-change cross-cutting spec shipped after Phase 1. The deployed
> agent image still predates **both** of these — see "Re-target without a
> rebuild" and "Teardown" below for what that means in practice.

### Run it

```bash
uv run run_curation.py            # RSS-only if TAVILY_API_KEY unset, else RSS + Tavily
uv run run_curation.py --force    # re-summarize everything (ignore dedup cache)
```

Discovery source is auto-selected: set `TAVILY_API_KEY` in `.env` (get one at
[tavily.com](https://tavily.com)) to pull from RSS + Tavily web search; leave it
unset to fall back to RSS alone (same behavior as Phase 0). Tuning knobs
(topic seeds, results-per-query, recency, domain filters, per-run cap) are
env-overridable — see `.env.example` and `src/curation/config.py`.

The Tavily key is **local-only** for now (`.env` / env var); Secrets Manager
resolution is deferred to `runtime-packaging`, once real cloud infra exists.

Output still lands in `.ai_radar_cache/cards.json` / `seen.json` by default (unchanged
from Phase 0 — the `JsonFileCardStore` default reproduces that behavior exactly).

#### Persistence backend

Store selection is env-driven (`CARD_STORE_BACKEND`, see `.env.example`):

- `json` (default) — local files, no AWS resources needed.
- `dynamo` — persists to a real DynamoDB table (`ai-radar-cards`), deduping via
  `BatchGetItem` instead of the local `seen.json` cache. Requires deploying the
  table first:

  ```bash
  npm install -g aws-cdk            # one-time: the CDK CLI (not a uv/Python package)
  uv sync --group infra
  uv run cdk bootstrap aws://<account-id>/us-east-1 --app "python infra/app.py"
  uv run cdk deploy --app "python infra/app.py"

  export CARD_STORE_BACKEND=dynamo
  uv run run_curation.py
  ```

  The table is provisioned on-demand (pay-per-request) with `RemovalPolicy.RETAIN`,
  so `cdk destroy` tears down the stack but never deletes real curated data. See
  [`specs/dynamodb-card-store/contract.md`](specs/dynamodb-card-store/contract.md)
  for the full key schema and behavior guarantees.

#### AgentCore Runtime deploy (`runtime-packaging`)

Packages the curation graph to run unattended in the cloud as an [AgentCore
Runtime](https://docs.aws.amazon.com/bedrock-agentcore/) agent instead of from
a laptop. `runtime_app.py` (repo root) wraps the **unchanged** compiled graph
in a `BedrockAgentCoreApp` handler, building `DynamoCardStore()` +
`RssDiscoverer` + (optionally) `TavilyDiscoverer` from env only — same wiring
as `run_curation.py`, minus the CLI/rich bits. The Tavily API key is resolved
from **AWS Secrets Manager at invocation time** (never baked into the image);
if the secret is missing/unreadable the run degrades to RSS-only. The
execution role is a custom least-privilege IAM role authored in CDK
(`infra/lib/agent_runtime.py` → `AgentRuntimeStack`) — the `agentcore` CLI is
told to use it and never allowed to auto-generate its own role. See
[`specs/runtime-packaging/contract.md`](specs/runtime-packaging/contract.md)
for the exact pinned trust/permission policies.

> **Toolkit note:** `bedrock-agentcore-starter-toolkit` (the `agentcore` CLI
> used below) prints a deprecation notice in favor of a new `@aws/agentcore`
> npm CLI, and `agentcore launch` has been renamed `agentcore deploy`
> (`launch` still works as an alias). The commands below use the current
> names; the toolkit still functions, this is just what's live as of
> 2026-07-28.

**Prerequisites**

- The `AiRadarCardStore` stack already deployed (`ai-radar-cards` table +
  `feed-by-score` GSI ACTIVE) — see the persistence-backend section above.
- `uv sync --group infra`; the `agentcore` CLI comes from the `dev` group
  (`uv sync`, already pulled in by `bedrock-agentcore-starter-toolkit`).
- A container engine (Docker/Finch/Podman) for local builds, **or** rely on
  the toolkit's default CodeBuild-based build (no local engine required). If
  building locally, the committed `Dockerfile` uses a BuildKit `RUN --mount=
  type=cache` instruction, so you need BuildKit enabled (Docker ≥23 / Finch
  default) — `DOCKER_BUILDKIT=1 docker build .` on older Docker.
- Bedrock model access to Claude Haiku 4.5 in `us-east-1` (see the table in
  `CLAUDE.md`); verify the `us.` inference profile's member regions:

  ```bash
  aws bedrock get-inference-profile \
    --inference-profile-identifier us.anthropic.claude-haiku-4-5-20251001-v1:0
  ```

  If they differ from `us-east-1`/`us-east-2`/`us-west-2`, update
  `haiku_regions` in `infra/lib/agent_runtime.py` (and the matching assertions
  in `tests/test_infra_agent_runtime.py`) before deploying.

**Deploy**

```bash
# 1. Deploy the execution role + placeholder Tavily secret (does NOT touch
#    the already-deployed AiRadarCardStore table).
uv run cdk deploy --app "python infra/app.py" AiRadarRuntimeRole
# capture the ExecutionRoleArn + TavilySecretArn outputs

# 2. Populate the real Tavily key — CDK/the image NEVER contain it. The
#    secret is seeded with curation.config.TAVILY_SECRET_UNSET_SENTINEL until
#    this runs; runtime_app.py treats that sentinel as "no key" (RSS-only).
aws secretsmanager put-secret-value \
  --secret-id ai-radar/tavily-api-key \
  --secret-string "<your-tavily-api-key>"

# 3. First-time setup needs `--create`. Point it at the CDK-authored role (do
#    not let it auto-create one) and opt in to an ECR repo under the naming
#    the IAM policy already scopes (`bedrock-agentcore-*`) — `--create` mode
#    refuses to provision ECR unless told to. AgentCore Memory is out of
#    scope for this spec, so disable it explicitly.
agentcore configure --create -n ai_radar_curation -e runtime_app.py \
  -er <ExecutionRoleArn> -r us-east-1 -ecr auto --disable-memory --non-interactive

# 4. Build (ARM64) + push to ECR + create the Runtime agent.
agentcore deploy

# 5. Inspect / invoke.
agentcore status
agentcore invoke '{}'   # payload is ignored — all config is env-driven
```

**Smoke test**

> **Since `async-invocation-ack`, `agentcore invoke '{}'` no longer returns
> the run's counts directly** — it acknowledges immediately
> (`{"status": "accepted", "run_id": …}`) and runs the curation pipeline as a
> background task, because EventBridge Scheduler's universal target has an
> undocumented ~30s response timeout and a curation run takes 25–35s (see
> `specs/async-invocation-ack/`, which closes
> `specs/eventbridge-schedule/audit.md` finding F5). The counts move to a
> `curation_run_complete` CloudWatch log record, joined to the ack by
> `run_id`. Verify in two steps:

```bash
# 1. Invoke — expect the ack shape in ~1s, not the pipeline's duration.
agentcore invoke '{}'
# {"status": "accepted", "run_id": "9f2c1b7e4a..."}

# 2. ~30-60s later, find the matching completion record in the runtime log
#    group (CloudWatch console, or `aws logs` against the log group/stream
#    from `agentcore status`) and confirm the card count moved.
#    curation_run_complete records look like:
#    {"event": "curation_run_complete", "run_id": "9f2c1b7e4a...",
#     "duration_s": 31.7, "discovered": 50, "deduped": 42, "summarized": 8,
#     "failed": 0, "persisted": 8, "discoverer_failures": 0,
#     "store_failures": 0, "tavily_enabled": true}
aws dynamodb scan --table-name ai-radar-cards --select COUNT

# 3. Re-invoke (after the first run's `curation_run_complete` record has
#    appeared, so you are not just re-hitting the single-flight guard).
agentcore invoke '{}'
```

Verified 2026-07-28 (pre-`async-invocation-ack`, when the ack shape still
carried the counts directly): first invoke returned
`{"discovered": 50, "summarized": 8, "persisted": 8, "tavily_enabled": true}`
and the table went 0 → 8. Re-invoking is **not** a no-op: `deduped` dropped
50 → 42 (the 8 already-stored cards were correctly excluded — dedup works),
but the table still grew to 16, because `AI_RADAR_MAX_ITEMS=8` caps how many
*new* items get summarized per run — a re-invoke picks up the next batch of
previously-undiscovered items rather than repeating the first one. That's the
intended incremental-curation shape (each scheduled run adds a bounded
slice), not a dedup bug. True idempotency only shows up once the discoverer
stops returning new candidates.

**Re-verified 2026-08-10, after `async-invocation-ack` redeployed** (ECR tag
`20260810-221147-104`): the two-step flow above is what was actually run, not
just documented. `agentcore invoke '{}'` returned
`{"status": "accepted", "run_id": "16f3c77a5b0a426e93d63f35c40cefb2"}`
immediately; the matching `curation_run_complete` record appeared **36.5s**
later — deliberately past the ~30s point where the old synchronous handler
would have caused an EventBridge Scheduler timeout — with card count moving
40 → 48 (one clean 8-card slice). See
[`specs/async-invocation-ack/audit.md`](specs/async-invocation-ack/audit.md)
(R11/T13) for the full CloudWatch evidence. **Not verified this session:** a
genuine back-to-back double-invoke against the deployed agent (to observe
`already_running` in production) — that guard is proven only by the offline
test suite so far.

**Re-target without a rebuild**: the same image reads `CARD_TABLE_NAME`,
`AWS_REGION`, `AI_RADAR_MAX_ITEMS`, `AI_RADAR_PER_FEED`, `CURATION_TAVILY_*`,
and `TAVILY_SECRET_NAME` from env — set them via `agentcore configure --env
KEY=VALUE` (or a redeploy of just the config) to point at a dev table with no
image rebuild.

> **Live image lags this rename (`rename-spike-to-shared`):** the deployed
> agent image still runs the pre-rename code, so it reads the pre-rename env
> key names, not the `AI_RADAR_*` ones above, until `agentcore deploy` is
> re-run — see `specs/rename-spike-to-shared/audit.md` for the exact old→new
> key mapping. Neither key is currently set on the runtime (it runs on code
> defaults), so this has no live effect today — but any `agentcore configure
> --env` re-targeting done before the redeploy must use the *old* names, not
> the ones documented above.

**Teardown**

> **Gotcha, confirmed by reading the toolkit's source (`operations/runtime/
> destroy.py`):** `agentcore destroy` does not know the difference between a
> role it auto-created and the CDK-authored role we pointed it at — it will
> happily `iam:DeleteRole` whatever ARN is in `.bedrock_agentcore.yaml`'s
> `aws.execution_role`, out from under CloudFormation, drifting the
> `AiRadarRuntimeRole` stack. Before destroying, null that one field so it
> skips IAM cleanup (you'll see `"No execution role configured, skipping IAM
> cleanup"` — that confirms it worked):
> ```bash
> # in .bedrock_agentcore.yaml, under agents.<name>.aws:
> #   execution_role: null
> ```
> The `codebuild.execution_role` field is a separate, toolkit-owned role
> (`AmazonBedrockAgentCoreSDKCodeBuild-...`) — safe to let `agentcore destroy`
> remove that one normally.

```bash
# 1. Toolkit-owned resources: Runtime endpoint, ECR images + repo, CodeBuild
#    project, its IAM role. Requires the execution_role edit above first.
agentcore destroy --force --delete-ecr-repo

# 2. CDK-owned resources: execution role + Tavily secret.
uv run cdk destroy --app "python infra/app.py" AiRadarRuntimeRole
```

The `ai-radar-cards` table is provisioned by the separate `AiRadarCardStore`
stack with `RemovalPolicy.RETAIN` and is untouched by either teardown step.

#### EventBridge Scheduler — daily automated trigger (`eventbridge-schedule`)

Automates the manual `agentcore invoke '{}'` above: a daily `EventBridge
Scheduler` schedule (`infra/lib/curation_schedule.py` → `AiRadarSchedule`
stack) calls the deployed Runtime agent unattended. EventBridge Scheduler has
**no native/templated target for Bedrock AgentCore Runtime**, so this uses the
generic `aws_cdk.aws_scheduler_targets.Universal` target instead, backed by a
15-minute flexible time window, 3 bounded retry attempts (not Scheduler's
default of 185), a 2-hour max event age, and an SQS dead-letter queue for runs
that exhaust every retry. The schedule **deploys `DISABLED`** — it exists and
costs nothing recurring until a human deliberately enables it.

**Prerequisites**

- The `runtime-packaging` agent deployed and `READY` (`agentcore status`) —
  see the deploy steps above.
- The `AiRadarCardStore` table `ACTIVE`.
- `uv sync --group infra` (same as the runtime-packaging prerequisites).

**1. Wire the agent ARN into SSM (manual, after every agent redeploy)**

CDK reads the agent's ARN as a deploy-time SSM dynamic reference
(`ssm.StringParameter.value_for_string_parameter`), because the ARN is created
by the `agentcore` CLI, outside CloudFormation. A human must write it *after*
`agentcore deploy`/`agentcore status` confirms the agent is `READY`:

```bash
agentcore status   # copy the value after "Agent ARN:"

aws ssm put-parameter --name /ai-radar/agent-runtime-arn \
  --type String --value "<agentRuntimeArn>" --overwrite
```

> **Gotcha, hit live during this feature's smoke test:** it is easy to paste
> the **wrong** ARN here. The agent's execution-role ARN
> (`arn:aws:iam::<account>:role/AiRadarRuntimeRole-AgentRuntimeExecutionRole...`)
> is superficially similar-looking to the real Runtime agent ARN
> (`arn:aws:bedrock-agentcore:<region>:<account>:runtime/<name>-<suffix>`) and
> pasting the role ARN in by mistake causes a **silent failure**: `cdk synth`/
> `deploy` succeed, the schedule looks fine, and every invocation lands
> straight in the DLQ with no other visible error. Always confirm against
> `agentcore status` → the `Agent ARN:` line (the `bedrock-agentcore:...
> runtime/...` one), never a CDK stack's execution-role output.

**2. Deploy the schedule stack (stays `DISABLED`)**

```bash
uv run --group infra cdk deploy --app "python infra/app.py" AiRadarSchedule
```

Verify it landed inert:

```bash
aws scheduler get-schedule --name <ScheduleName-output> --group-name default \
  --query "{State:State,Expr:ScheduleExpression,Tz:ScheduleExpressionTimezone}"
# {"State": "DISABLED", "Expr": "cron(0 6 * * ? *)", "Tz": "Etc/UTC"}
```

**3. One-shot live fire (safe way to prove the wire format for real)**

Rather than flipping on the daily cadence, redeploy once with a one-time cron
expression a few minutes in the future (UTC, explicit year so it matches
exactly once) and `schedule_enabled=true`:

```bash
uv run --group infra cdk deploy --app "python infra/app.py" AiRadarSchedule \
  -c schedule_enabled=true \
  -c schedule_expression="cron(<MM> <HH> <DD> <month> ? <YYYY>)"
```

Wait up to 15 minutes (the flexible window), then check:

```bash
aws dynamodb scan --table-name ai-radar-cards --select COUNT   # count should move by one bounded slice

# Since async-invocation-ack, confirm exactly one run fired by counting
# curation_run_complete records in the window — don't rely on DLQ-empty
# alone (see the gotcha below):
aws logs filter-log-events --log-group-name <RuntimeLogGroup> \
  --start-time <fire-time-epoch-ms> --filter-pattern '"curation_run_complete"'
  # expect exactly one record

aws sqs get-queue-attributes \
  --queue-url <DeadLetterQueueUrl-output> \
  --attribute-names ApproximateNumberOfMessages   # should be 0
```

**Verified 2026-08-10 (live fire, real AWS — first attempt, pre-`async-invocation-ack`):**
card count rose 24 → 40, not 32 as first logged (a mid-run sample undercounted
— see `specs/eventbridge-schedule/audit.md` finding F6), because the fire
actually **delivered twice**. This surfaced a real bug (finding F5, HIGH):
the `Universal` target is **synchronous with an undocumented ~30s response
timeout**, and the curation run took 25–35s, so Scheduler treated the
slow-but-successful response as a failure, retried it, and ran the whole
curation pipeline a second time. The DLQ-empty check above passed cleanly
throughout and gave false confidence — see the gotcha below.

> **Gotcha — check `AWS/Scheduler`'s `TargetErrorCount` directly, don't infer
> single-delivery from an empty DLQ (F5, RESOLVED by `async-invocation-ack`):**
> DLQ depth only reflects deliveries that exhausted every retry attempt; a
> delivery can be retried — and re-run the entire pipeline — without ever
> reaching the DLQ. Query the `TargetErrorCount` metric for the fire's time
> window if you need to be sure only one delivery happened.

**Fixed and re-verified 2026-08-10, later the same day:** after redeploying
the agent with [`async-invocation-ack`](specs/async-invocation-ack/)'s
immediate-ack entrypoint (see the spec table above and the smoke-test section
above), a fresh one-shot fire against the redeployed agent produced exactly
**one** delivery: `InvocationAttemptCount=1`, **zero** `TargetErrorCount`
datapoints, one `curation_run_complete` record, and a clean 48→56 card-count
slice (not two). DLQ stayed at 0. Full evidence:
[`specs/async-invocation-ack/audit.md`](specs/async-invocation-ack/audit.md)
(R12/T14), and the dated F5-resolution entry in
[`specs/eventbridge-schedule/audit.md`](specs/eventbridge-schedule/audit.md)'s
Audit Log. **Not verified:** the prescribed double-fire dedup drill (does a
double-*delivery* skip re-curating an already-stored URL) was never run as
its own test — only incidentally observed during the original F5 bug, where
the two runs happened to curate 16 disjoint URLs with zero overlap.

> **Wire-format gotcha (load-bearing, don't "fix" it):** the `Universal`
> target's `service` prop must be `"bedrockagentcore"` (the botocore/SDK
> **service identifier**), which is deliberately a *different* string from the
> IAM action prefix `bedrock-agentcore:InvokeAgentRuntime` (the **signing
> name**). Both spellings are correct in their own place
> (`infra/lib/curation_schedule.py`'s `UNIVERSAL_TARGET_SERVICE` vs.
> `INVOKE_IAM_ACTION`) — harmonizing them to match reintroduces a defect. The
> target `Input` payload also uses **PascalCase** member names
> (`AgentRuntimeArn`, `RuntimeSessionId`, `ContentType`, `Payload`), with
> `Payload` sent as a **plain UTF-8 JSON string** (`"{}"`, not base64). Both
> details were unverifiable by `cdk synth` alone — only the live fire above
> proved them.

**4. Return to inert**

A plain redeploy (no `-c` flags) always restores the safe default:

```bash
uv run --group infra cdk deploy --app "python infra/app.py" AiRadarSchedule
```

**Going live for real** — enables the actual daily 06:00 UTC cadence, which
starts real recurring cost (one AgentCore Runtime curation run per day, Haiku-
only, capped by `AI_RADAR_MAX_ITEMS`):

```bash
uv run --group infra cdk deploy --app "python infra/app.py" AiRadarSchedule \
  -c schedule_enabled=true
```

**Pausing** without destroying anything — same command, `schedule_enabled`
omitted (falls back to `DISABLED`) or explicitly `-c schedule_enabled=false`.

**Teardown**

```bash
uv run --group infra cdk destroy --app "python infra/app.py" AiRadarSchedule
```

Removes the schedule, the DLQ, and the CDK-created Scheduler invoke role. The
`ai-radar-cards` table, the SSM parameter, and the Spec 04 execution role/agent
all survive (none of them are owned by this stack). If you are also tearing
down the agent itself afterward, the **same `runtime-packaging` gotcha above
still applies**: null `aws.execution_role` in `.bedrock_agentcore.yaml` before
`agentcore destroy`, or it deletes the CDK-owned execution role out from under
`AiRadarRuntimeRole`.

**Current live AWS state (as of 2026-08-12):** four CDK stacks are deployed
and **not** torn down — `AiRadarCardStore`, `AiRadarRuntimeRole`,
`AiRadarSchedule`, and (new from `run-observability`) `AiRadarBudget`. The
`runtime-packaging` agent (`ai_radar_curation`) is running image tag
`20260812-162922-638` (rebuilt during `run-observability`'s live fire; it
supersedes the `async-invocation-ack` image `20260810-221147-104` and carries
the same immediate-ack entrypoint plus the new token/metrics instrumentation).
The schedule itself is back to its safe default (`DISABLED`,
`cron(0 6 * * ? *)` @ `Etc/UTC`) — it has not fired since the one 2026-08-10
one-shot test; the only run since then is the single manual
`agentcore invoke '{}'` used to verify `run-observability` (below), **not** an
unattended scheduled run. `ai-radar-cards` holds 80 items. The `AiRadarBudget`
stack's SNS topic (`ai-radar-budget-alerts`) has one confirmed email
subscriber. All four stacks/resources are live infrastructure incurring some
ongoing (non-recurring-run) cost exposure until someone runs the teardown
steps above, in the `runtime-packaging` section, and below (`AiRadarBudget`).

#### Run observability (`run-observability`)

Every curation run now produces a `RunSummary` (`src/curation/summary.py`) —
discovered (total, plus RSS-vs-Tavily split and per-source counts), dedup/
summarize/persist counts, Bedrock input/output tokens, Tavily searches/
credits, and three cost figures (`estimated_bedrock_cost_usd` +
`estimated_tavily_cost_usd` = `estimated_cost_usd`). It shows up in three
places:

1. **`curation_run_complete`** (CloudWatch, via the existing
   `bedrock_agentcore.app.curation` logger) — a strict superset of the eight
   fields shipped by `async-invocation-ack`; nothing renamed or removed.
2. **`curation_run_metrics`** — one raw JSON line written directly to
   `stderr` (bypassing `logging` on purpose — the SDK's formatter would nest
   it under a `message` string and break the CloudWatch *embedded metric
   format* spec's "no additional data" rule). CloudWatch Logs parses it into
   4 custom metrics in namespace `AIRadar/Curation`: `RunsCompleted`,
   `CardsWritten`, `ItemsFailed`, `EstimatedCostUsd` — no dimensions, so
   cardinality is fixed at 4 regardless of run count (~$1.20/month). Set
   `CURATION_EMIT_METRICS=false` to stop emitting it entirely (logs stay the
   full record either way).
3. **Locally** — `uv run run_curation.py` builds the identical `RunSummary`
   and prints it (no EMF line locally; there is no CloudWatch to parse it).

**Two Logs Insights queries** answer "failed counts for the last 7 runs" —
prefer the first (top-level fields) when metrics are enabled; the second
works even with the kill switch on, since it reads the logger record instead
(payload nested one level under `message` — see the contract's Data Models
section for why):

```sql
-- preferred: the EMF line, top-level fields
fields @timestamp, run_id, discovered, failed, cards_written, estimated_cost_usd
| filter event = "curation_run_metrics"
| sort @timestamp desc
| limit 7

-- fallback: the logger record (works even with CURATION_EMIT_METRICS=false)
fields @timestamp, @message
| filter @message like /curation_run_complete/
| sort @timestamp desc
| limit 7
```

**AWS Budget (`AiRadarBudget` stack, `infra/lib/cost_budget.py` +
`infra/stacks/cost_budget_stack.py`)** — a new, CDK-managed monthly `COST`
budget `ai-radar-monthly-cost` with `ACTUAL`/`GREATER_THAN`/`ABSOLUTE_VALUE`
notifications at $50/$100/$250 via SNS email, `IncludeCredit: false` (so the
credit-covered account doesn't report ~$0 forever). It is entirely separate
from — and never touches — the pre-existing, hand-made "My Monthly Cost
Budget" ($1/mo).

```bash
# Deploy (independent of the agent/schedule stacks; cheap — first two AWS
# Budgets are free, SNS is within free tier):
uv run --group infra cdk deploy --app "python infra/app.py" AiRadarBudget

# Confirm the SNS email subscription (required — AWS Budgets notifications
# are silently dropped otherwise), then prove delivery:
aws sns list-subscriptions-by-topic --topic-arn <AlertTopicArn>   # not "PendingConfirmation"
aws sns publish --topic-arn <AlertTopicArn> --subject "AI Radar budget test" --message "live-fire check"

# Teardown — removes the budget, its topic, and the subscription; the
# hand-made "My Monthly Cost Budget" is untouched (distinct name, never
# CloudFormation-managed):
uv run --group infra cdk destroy --app "python infra/app.py" AiRadarBudget
```

**Verified live, 2026-08-12** (full evidence in
[`specs/run-observability/audit.md`](specs/run-observability/audit.md)'s
Phase-6 re-audit, independently re-derived by the auditor from live AWS, not
accepted from the executor's report): `cdk deploy AiRadarBudget` created the
budget cleanly in ~15s, and `cdk diff` on the three pre-existing stacks stayed
empty; `aws budgets describe-budgets` shows `ai-radar-monthly-cost`
(COST/MONTHLY/$250, `IncludeCredit: false`) with all three 50/100/250
notifications `OK`, alongside the pre-existing, hand-made "My Monthly Cost
Budget" — untouched; the SNS email subscription was confirmed (real ARN, not
`PendingConfirmation`) and a real `aws sns publish` test message arrived in
the inbox; `agentcore deploy` pushed image `20260812-162922-638`; a real
`agentcore invoke '{}'` (`run_id d577c1c0c1a240edabb5b6d461a15c07`) produced
all six expected CloudWatch records including the raw `curation_run_metrics`
EMF line — confirmed to land as its **own** top-level-JSON log event, not
nested under a logger `message` wrapper, settling the spec's single biggest
design risk — and `aws cloudwatch list-metrics --namespace AIRadar/Curation`
returned exactly the 4 designed metrics with datapoints; `ai-radar-cards`
grew 72 → 80 (+8, one bounded slice). One post-audit hardening (`O1`) also
landed: `summarize_with_usage`'s degradation guard now also catches
`AttributeError` (a non-mapping `usage` value), taking the suite to 145
tests.

**Cost-figure caveat, worth knowing when reading `estimated_cost_usd`:** on
this run, $0.04 of the $0.063358 total was the *Tavily estimate* (Tavily's
API doesn't report actual credits consumed, so it's attempted-searches ×
credits-per-depth × a configured unit price) — only $0.023358 was measured
Bedrock spend (and that figure matched AWS's own `AWS/Bedrock` CloudWatch
token metrics **exactly**, delta $0.00). Treat `EstimatedCostUsd` as a
budgeting signal, not an invoice, until `CURATION_TAVILY_CREDIT_PRICE_USD` is
set to a real negotiated rate. Separately, the two AWS Budgets in this
account reported slightly different actual spend for the same month
(`My Monthly Cost Budget`: $5.322 vs. `ai-radar-monthly-cost`'s
`IncludeCredit: false`: $5.382) — live proof that the credit-exclusion design
choice does something real on a credit-covered account, not just in theory.

**Not verified / deliberately not claimed:** the schedule remains `DISABLED`,
so no unattended/scheduled run has ever produced these records — only the one
manual invoke above. `CURATION_EMIT_METRICS=false` (the metrics kill switch)
was never actually exercised live; it's covered by an offline test only.

### Tests

```bash
uv run pytest tests/ -v   # 261 tests, all offline (Bedrock/Tavily stubbed, DynamoDB via moto, CDK via synth-only assertions, AgentCore handler mocked)
```

Live API/AWS calls (Bedrock, Tavily, real DynamoDB, the real `cdk deploy` +
`agentcore deploy` + smoke invoke above) only happen via the manual runbook
steps — never in the automated suite.

## Phase 0 spike (reference baseline)

Proves the core curation loop end-to-end with **zero infra**, using real Amazon Bedrock:

```
discover (RSS)  →  dedup  →  summarize + tag (Claude Haiku 4.5)  →  rank  →  print cards
```

This validates summary quality — the thing worth checking before any AWS infra goes up.

### Run it

Uses [uv](https://docs.astral.sh/uv/) as the package manager.

```bash
uv sync                       # create .venv + install from the lockfile
uv run run_curation.py           # curation loop (skips already-seen items)
uv run run_curation.py --force   # re-summarize everything
uv run run_chat.py            # ask questions about the curated cards (RAG)
```

AWS credentials are read from `~/.aws` by default; copy `.env.example` → `.env` only to
override region/models. Requires Bedrock model access to Claude Haiku 4.5, a Sonnet
chat model, and Titan Embeddings v2 in your region.

### What it does

| Step | Where | Notes |
|---|---|---|
| Discover | `src/shared/feeds.py` | Pulls recent entries from curated AI/ML RSS feeds (no API key). |
| Dedup | `src/curation/local.py` (`JsonFileCardStore`) | URL-hash cache in `.ai_radar_cache/seen.json` → idempotent re-runs; reproduces the retired Phase 0 `pipeline.py`'s behavior exactly (see git history). |
| Summarize + tag | `src/shared/bedrock.py` | Bedrock Converse with a **forced tool call** → guaranteed structured cards. |
| Rank + render | `src/shared/cards.py` | Sort by model relevance score; pretty console panels. |

Output is also written to `.ai_radar_cache/cards.json` for inspection.

### Mini RAG chat (Plane B preview)

`uv run run_chat.py` runs a grounded chatbot over the curated cards:

| Step | Where | Notes |
|---|---|---|
| Embed cards | `src/shared/retrieval.py` | Titan v2 embeddings, cached in `.ai_radar_cache/embeddings.json`. |
| Retrieve | `src/shared/retrieval.py` | In-memory cosine top-k (normalized → dot product). |
| Answer | `src/shared/chat.py` | Sonnet, grounded in retrieved cards, inline `[n]` citations, multi-turn memory. |

It answers only from retrieved cards (no hallucination) and says so when the corpus
lacks the answer. The stable system prompt uses a Bedrock prompt-cache point.

### Deliberately deferred (superseded by Phase 1 progress above, or still later)

- ~~**Search API** (Tavily/Exa)~~ — done, see `tavily-discovery` above.
- ~~**LangGraph orchestration**~~ — done, see `curation-graph` above.
- ~~**DynamoDB card persistence**~~ — done, see `dynamodb-card-store` above. A real vector store for RAG (Phase 3) is still deferred — the table reserves an unpopulated `embedding` attribute for it.
- ~~**AgentCore Runtime packaging**~~ — done and deploy-verified, see `runtime-packaging` above.
- ~~**EventBridge scheduling**~~ — done and live-fire verified, see `eventbridge-schedule` above. Deploys `DISABLED`; going live is a deliberate opt-in (real recurring cost). The first live fire hit a real duplicate-run bug (Scheduler's ~30s synchronous timeout, finding F5) — fixed by `async-invocation-ack`.
- ~~**Async invocation acknowledgment**~~ — done and live-fire verified, see `async-invocation-ack` above. Fixes F5; `agentcore invoke '{}'` now returns an ack, not the run's counts (see the smoke-test section above).
- **AgentCore Memory** — chat memory is an in-process list; becomes AgentCore Memory (STM/LTM) in a later phase (Plane B, untouched by Phase 1).

### Config knobs (`.env` or env vars)

`AWS_REGION`, `HAIKU_MODEL_ID`, `AI_RADAR_MAX_ITEMS`, `AI_RADAR_PER_FEED` — see `.env.example`.

Both config modules (`src/shared/config.py`, `src/curation/config.py`) load via
`pydantic-settings` (see `pydantic-settings-config` above), so every override
is validated at startup, not silently accepted: an unparseable value (e.g.
`HAIKU_INPUT_USD_PER_1M=abc`) raises a `pydantic.ValidationError` at import,
naming the exact env var, instead of a bare `ValueError` or a wrong value that
only shows up later.

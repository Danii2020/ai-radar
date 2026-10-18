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
> zero-behavior-change cross-cutting spec shipped after Phase 1. **Redeployed
> 2026-08-30** — the live agent image now includes both of these; see
> "Current live AWS state" below for the redeploy evidence. The
> `AI_RADAR_*` env key names in "Re-target without a rebuild" below are now
> the live ones.

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

> **Resolved 2026-08-30:** the deployed agent image was redeployed and now
> runs post-rename code, so it reads the `AI_RADAR_*` env key names above
> (see "Current live AWS state" below for the redeploy evidence) — the old
> pre-rename key names no longer apply to `agentcore configure --env`
> re-targeting.

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

**Previous live AWS state (account `536697225154`, as of 2026-08-30 — superseded by "Account migration (2026-10-05)" below):** four CDK stacks are deployed
and **not** torn down — `AiRadarCardStore`, `AiRadarRuntimeRole`,
`AiRadarSchedule`, and `AiRadarBudget`. The `runtime-packaging` agent
(`ai_radar_curation`, runtime ID `ai_radar_curation-sIf5Dw979w`) is running
image tag `20260830-213649-798`, redeployed 2026-08-30 via `agentcore
configure --create` + `agentcore deploy --auto-update-on-conflict` (the local
`.bedrock_agentcore.yaml` toolkit state file had gone missing on this
machine — regenerating it via `--create` and updating in place, rather than
`agentcore import`, is what the installed toolkit version supports; the
existing ECR repo and runtime ID were reused, not duplicated). This closes
the drift called out in the "Cross-cutting specs" section below: the live
agent now runs the **same code as `main`**, including both
`rename-spike-to-shared` (`AI_RADAR_*` env keys) and
`pydantic-settings-config`, superseding the `run-observability` image
`20260812-162922-638`. Verified via the standard two-step smoke test:
`agentcore invoke '{}'` → immediate ack (`run_id 36711e4e...`), then a
`curation_run_complete` record ~2.5 min later (longer than the usual 25–35s
because the `BAIR Blog` RSS feed hit a connection timeout that run — handled
gracefully, `failed: 0`, `discoverer_failures: 0` — not a regression) with
`persisted: 8`, all 4 `AIRadar/Curation` EMF metrics present, and
`ai-radar-cards` moving 80 → 88. The schedule itself is unchanged and still
at its safe default (`DISABLED`, `cron(0 6 * * ? *)` @ `Etc/UTC`) — it has
not fired since the one 2026-08-10 one-shot test; every run since then
(including this redeploy's smoke test) has been a manual
`agentcore invoke '{}'`, **not** an unattended scheduled run — so Task 4.7
(the double-fire dedup drill) is still open. The `AiRadarBudget` stack's SNS
topic (`ai-radar-budget-alerts`) has one confirmed email subscriber. All four
stacks/resources are live infrastructure incurring some ongoing
(non-recurring-run) cost exposure until someone runs the teardown steps
above, in the `runtime-packaging` section, and below (`AiRadarBudget`).

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
uv run pytest tests/ -v   # 350 tests, all offline (Bedrock/Tavily stubbed, DynamoDB via moto, CDK via synth-only assertions, AgentCore handler mocked, feed-api Lambda handler tested against moto)
```

Live API/AWS calls (Bedrock, Tavily, real DynamoDB, the real `cdk deploy` +
`agentcore deploy` + smoke invoke above) only happen via the manual runbook
steps — never in the automated suite. (This count now includes `feed-api`'s
tests too — see "Phase 2 — Web Feed" below; there is no separate `pytest`
invocation per phase.)

## Phase 2 — Web Feed (1 of 2 specs implemented and deployed)

Design §8's Phase 2 deliverable is *"I can open a URL and see the cards."*
Two specs make that true: `feed-api` (a real, versioned HTTP contract in
front of DynamoDB) and `web-feed-ui` (the Next.js frontend that consumes it).
See [`tasks/phase-2-web-feed/`](tasks/phase-2-web-feed/) for the plan and
[`specs/`](specs/) for each spec's contract.

| Spec | Status | What it added |
|---|---|---|
| [`feed-api`](specs/feed-api/) | ✅ Deployed & live-curl-verified | `GET /v1/cards` (API Gateway HTTP API → Lambda → `dynamodb:Query` on `feed-by-score`, cursor pagination, `?tag=`/`?limit=` filtering) plus the versioned `CardOut`/`FeedResponse` Pydantic contract (`src/contracts/card.py`) and its committed JSON Schema artifact. Details below. |
| [`web-feed-ui`](apps/web/specs/archived/web-feed-ui/) | ✅ Locally verified (build/lint/typecheck/test all green); **Vercel deploy + CORS redeploy still pending (human step, AD-10)** | `apps/web/` — the repo's first frontend: Next.js 16 (App Router) + React 19, server-rendered feed at `/`, tag filtering and cursor pagination via plain links, a generated+drift-tested `CardOut`/`FeedResponse` TypeScript mirror of `feed-api`'s schema artifact, and a bounded empty-page drain for `feed-api`'s Guarantee 4. Details below. |
| [`feed-structure-refactor`](apps/web/specs/archived/feed-structure-refactor/) | ✅ Locally verified (87 unit + 23 Playwright e2e tests green); shipped 2026-10-03, audit APPROVED WITH RESERVATIONS | `apps/web/` — zero-behavior-change split of `features/feed/` into `api/`, `components/`, `lib/` behind a single `index.ts` entry point, plus an offline Playwright e2e tier. Details below. |

### `feed-api` — read-only feed HTTP API

**What's actually verified, offline, 2026-09-01/02** (audited **APPROVED WITH
RESERVATIONS** by `sdd-auditor` — every one of contract.md's 15 Behavior
Guarantees checked against the implementation text and holds; 14/16
requirements PASS at that time, the other 2 needed a live deploy — since
closed by the 2026-09-03 deploy + 2026-09-04 live-curl verification below):

- `uv run pytest tests/` → **349 passed, 0 failed**, fully offline
  (moto-backed DynamoDB, `Template.from_stack` CDK synth, re-verified by the
  auditor under scrubbed AWS credentials).
- New code: `src/contracts/card.py` (`CardOut`/`FeedResponse`,
  `CARD_SCHEMA_VERSION = "v1"`), `src/api/{config,cursor,dynamo,feed,handler}.py`,
  `Dockerfile.feed_api`, `infra/lib/feed_api.py` (`FeedApi` construct) +
  `infra/stacks/feed_api_stack.py` (`FeedApiStack`, wired into `infra/app.py`
  as a new, not-yet-deployed stack `AiRadarFeedApi`), `export_api_schema.py`
  + the committed `docs/api/feed-api.v1.schema.json`.
- IAM is genuinely least-privilege (dumped and inspected by the auditor):
  the synthesized role has exactly two statements — `dynamodb:Query` on the
  single `feed-by-score` index ARN only (no base-table ARN, no wildcard) and
  a `logs:CreateLogStream`/`PutLogEvents` grant scoped to the function's own
  log group — no managed policy anywhere, no write action anywhere.
- **The Lambda image was actually built and smoke-tested locally**
  (2026-09-02): `docker build -f Dockerfile.feed_api --platform linux/arm64
  -t ai-radar-feed-api-local-check .` from the repo root succeeded, and
  `import api.handler, contracts.card` plus a full `handler()` call against a
  fake table returned a correct 200 empty-feed response **inside the built
  image**. Image size ≈ 843 MB total (≈ 590 MB is the AWS base Lambda Python
  3.12 image; this spec's own layers are ≈ 44 MB: 36 MB `uv` binary + 7.65 MB
  `pydantic`/`pydantic-settings` + ~70 KB app code). The local test image was
  removed afterward (`docker rmi`) — **nothing was pushed to any registry,
  and no `cdk deploy` was run.**

> **Packaging gotcha (a real bug found this way, not a hypothetical) —
> verify a Docker-image-Lambda's `uv --only-group` closure by actually
> building the image, not by `pytest` passing.** `src/api/config.py` is a
> `pydantic-settings` `BaseSettings` module, but `pyproject.toml`'s `api`
> dependency group initially listed only `pydantic`. Every offline `pytest`
> run stayed green anyway, because `pydantic-settings` was already present in
> the dev `.venv` as a *main*-group dependency — the gap was invisible until
> the image was actually built with `--only-group api` and
> `import api.handler` inside it raised `ModuleNotFoundError: No module named
> 'pydantic_settings'`. Fixed with `uv add --group api pydantic-settings`
> (now `api = ["pydantic>=2.13.4", "pydantic-settings>=2.14.2"]`); rebuilt,
> re-verified. **Lesson for the next Docker-image-Lambda spec** (this repo's
> established AD-1 packaging pattern, likely reused by Phase 3's chat
> endpoint): a dev-group dependency can mask a missing prod dependency
> indefinitely if you only ever run tests inside the repo's own `.venv` — the
> only real check is building the image and importing inside it.

**Live deploy + curl verification (2026-09-03, `AiRadarFeedApi` stack,
`CREATE_COMPLETE`, original account `536697225154`).** Deployed outside this conversation (no commit records
the `cdk deploy` itself — confirmed against real AWS on 2026-09-04 via
`aws cloudformation describe-stacks` and re-verified live with fresh curls
before starting `web-feed-ui`):

- **Stack outputs** (original account; the migrated account's URL is under "Account migration"): `FeedApiUrl = https://fdcksuokyh.execute-api.us-east-1.amazonaws.com`,
  `FeedApiFunctionName = ai-radar-feed-api`,
  `FeedApiLogGroupName = /aws/lambda/ai-radar-feed-api`,
  `FeedApiAllowedOrigins = http://localhost:3000` (still the pre-Vercel
  default — `web-feed-ui` updates this to the real deployed Vercel origin).
- **`GET /v1/cards?limit=2`** → real `ai-radar-cards` items, 200.
- **Cursor pagination**: `?limit=2&cursor=<next_cursor>` → a disjoint next
  page (verified card IDs don't repeat).
- **Tag filter**: `?tag=security&limit=3` → all 3 returned cards carry
  `security`.
- **Validation**: `?limit=0` → `400 {"error": "invalid_limit", ...}`.
- **CORS**: `Origin: http://localhost:3000` → `access-control-allow-origin`
  echoed back; an unlisted origin (`https://evil.example.com`) gets no
  CORS header at all (correctly rejected).
- **AD-6 resolved**: the index-only `dynamodb:Query` IAM grant (no base-table
  ARN) is sufficient — no `AccessDeniedException`, so the
  `grant_base_table_query=True` fallback was never needed.
- **AD-7 deviation, live-observed**: the deployed function's
  `ReservedConcurrentExecutions` is `null` (unreserved), not AD-7's intended
  `5` — consistent with `infra/lib/feed_api.py`'s documented
  `-c feed_api_reserved_concurrency=none` account-quota bridge (this
  account's Lambda concurrent-executions quota is still 10, the same
  constraint `runtime-packaging` hit). Endpoint throttling
  (`ThrottlingRateLimit=20`/`ThrottlingBurstLimit=40`) still applies at the
  API Gateway edge regardless. Worth flipping back to reserved `5` if/when
  the account quota increase lands.

Teardown, if ever needed: `uv run cdk destroy --app "python infra/app.py"
AiRadarFeedApi` — the RETAINed `ai-radar-cards` table survives (this stack
only ever references it by name, never creates it); the image's ECR asset
does not auto-delete and needs its own cleanup.

This section will be updated with real curl output, real counts, and the
AD-6 resolution once Phase 6 actually runs — see
[`specs/feed-api/audit.md`](specs/feed-api/audit.md)'s Final Verdict and
Manual/live-verification table for the full list of what remains pending.

### `web-feed-ui` — the Next.js feed frontend

**What's verified, offline, 2026-09-18** (see
[`apps/web/specs/archived/web-feed-ui/audit.md`](apps/web/specs/archived/web-feed-ui/audit.md) for the full
requirement-by-requirement table):

- `apps/web/` is a Next 16.3.5 / React 19.2.8 / TypeScript App Router project,
  npm-only (`package-lock.json`, no workspaces), living alongside — not
  replacing — the Python backend. Nothing under `src/`, `tests/`, `infra/`,
  `docs/api/`, `pyproject.toml`, or `uv.lock` was touched by this spec.
- `features/feed/api/types.generated.ts` is generated by `npm run generate:types`
  from the committed `docs/api/feed-api.v1.schema.json` (via
  `json-schema-to-typescript`, `additionalProperties: false`) and drift-tested:
  regenerating in-memory must reproduce the committed file byte-for-byte, and
  a second test asserts the field-name sets against the artifact's own
  `properties` keys.
- `features/feed/api/client.ts`'s `fetchFeed()` is the **only** module that calls
  `fetch` — exactly one request per call, `limit` always present, `tag`/
  `cursor` present iff non-empty, `cursor` passed through byte-identical,
  `{ next: { revalidate: 300 } }` for Next's Data Cache, and a per-card
  `isCardOut` runtime guard (types are erased at runtime) that drops and
  counts malformed cards rather than failing the whole page.
- `features/feed/api/load-feed.ts`'s `loadFeed()` implements the AD-6 bounded
  drain: `feed-api`'s Guarantee 4 means `?tag=<x>` can return `{"cards": [],
  "next_cursor": "<token>"}` — an empty page with a *live* cursor — live-
  verified against the deployed API (`?tag=zzz-no-such-tag&limit=5`, probed
  2026-09-04). `loadFeed` follows the cursor while the page is empty, up to
  `MAX_DRAIN_REQUESTS = 5`, and never claims "no matches" for a page it
  never read.
- Four exhaustive, distinctly-tested UI states (`feed-list` / `feed-empty` /
  `feed-no-match` / `feed-error`), each a stable `data-testid` asserted by
  `features/feed/components/feed-view.test.tsx` — no blank page, no unhandled exception,
  no client-side re-sort (`features/feed/conventions.test.ts` greps for
  `.sort(`/`.reverse(` under `features/feed/` and fails if either appears).
- All fetching is server-side (AD-4): no `NEXT_PUBLIC_*` variable and no
  `"use client"` module imports `api/client.ts`/`api/load-feed.ts`, both grep-asserted
  by `conventions.test.ts`. `FEED_API_BASE_URL` is read lazily inside
  `feedApiBaseUrl()` — never at module import — so `npm run build` succeeds
  with the variable **unset** (verified this session: `mv .env.local
  /tmp && rm -rf .next && npm run build` → exit 0).
- Styling is CSS Modules only, using two hand-authored design deliverables
  copied byte-verbatim (diffed, not hand-edited) from
  `apps/web/specs/archived/web-feed-ui/claude-design-outputs/`: `tokens.css` →
  `apps/web/app/globals.css` and `feed.module.css` →
  `apps/web/features/feed/components/feed.module.css`.
- Local green gates, all exit 0 in `apps/web/`: `npm test` (8/8 files, 55/55
  tests — covers T1–T33 from `audit.md`'s Test Coverage table), `npm run
  lint` (0 errors; one pre-existing warning on the generated file's own
  `/* eslint-disable */` banner, which is never hand-edited), `npm run
  typecheck` (`tsc --noEmit`), `npm run build` (`next build`, Turbopack).
- Backend untouched: `uv run pytest tests/` → 350 passed (the spec's
  documented baseline was 349 as of 2026-09-04; the +1 predates this
  implementation session — `git status --porcelain` confirms zero diff under
  `src/`, `tests/`, `infra/`, `docs/api/`, `pyproject.toml`, `uv.lock`,
  `Dockerfile*` throughout this work).

**Not yet done, by design (AD-10 — deployment is a human step):** no Vercel
project exists yet and `feed-api`'s CORS allow-list still only contains
`http://localhost:3000`. See "Run the web feed locally" below for the
executor-verifiable local check, and the Phase 5 runbook after it for the
exact human steps to take it live.

**Open question, recorded per AD-9 (house style — see `feed-api` AD-6):**
whether passing `signal: AbortSignal.timeout(FETCH_TIMEOUT_MS)` on the feed
fetch disables Next's Data Cache for that request is not settled by the Next
16 docs. The `fetch` API reference's `options.next.revalidate` section makes
no mention of `signal` at all; the same page's Memoization section *does*
document that passing an `AbortController`/`AbortSignal` opts a request out
of Next's **per-render-pass memoization** (a different, shorter-lived
mechanism than the persistent Data Cache) — which is expected and harmless
here, since `loadFeed`'s drain hops use distinct URLs (different cursors)
that would never have memoized against each other anyway. No documented
interaction between `signal` and `next.revalidate` was found either way.
`signal` is being **kept** (it bounds a hung upstream call to 8s instead of
letting API Gateway's full 30s hold a render open) pending the live
dev-server repeat-view check in the Phase 5/Task 4.11 runbook below, which
can observe directly whether a second view within 300s re-hits the API. See
`apps/web/specs/archived/web-feed-ui/audit.md`'s Audit Log (2026-09-18 entry) for the full
finding.

### `feed-structure-refactor` — feed folder split by role, Playwright e2e tier

Shipped 2026-10-03 (audit: APPROVED WITH RESERVATIONS, round 1; the WEB-11 local
smoke check against the real `feed-api` was run by hand and passed). A
zero-behavior-change refactor of `apps/web/features/feed/`; see
[`apps/web/specs/archived/feed-structure-refactor/`](apps/web/specs/archived/feed-structure-refactor/).

- `features/feed/` is split into `api/` (`client.ts`, `load-feed.ts`,
  `load-feed-state.ts`, `types.generated.ts`), `components/` (`feed-view.tsx`,
  `card-item.tsx`, `tag-filter.tsx`, `pagination.tsx`, `feed.module.css`) and
  `lib/` (`href.ts`, `tags.ts`, `search-params.ts`), each test beside its source.
  Only `index.ts` and `conventions.test.ts` stay at the feature root.
- `features/feed/index.ts` is the only public surface (three runtime exports:
  `FeedView`, `loadFeedState`, `parseFeedSearchParams`). `app/page.tsx` is now an
  11-line shell that imports only from it; the search-param parsing and the
  `feed_fetch_failed` error-to-state mapping moved into the tested
  `lib/search-params.ts` and `api/load-feed-state.ts`. Guards in
  `conventions.test.ts` fail on deep imports from outside the feature, barrel
  self-imports, and any `"use client"` import of the barrel or `api/`.
- `feed.module.css` and `types.generated.ts` moved byte-identical (same SHA-256);
  `npm run generate:types` now writes to `features/feed/api/types.generated.ts`.
- New end-to-end tier: `@playwright/test` (devDependency) runs 23 scenarios via
  `npm run test:e2e` against a local `node:http` stub of `feed-api` (no AWS
  traffic), comparing normalized DOM, computed styles and console output with a
  baseline captured from the pre-refactor app. CSS-module class hashes are
  normalized because moving the CSS file changes them by design.
- Local gates: `npm test` 87/87, `npm run test:e2e` 23/23, lint, typecheck and
  build green.
- Reservations: audit F3 — the duplicate web workflow was resolved by removing
  the hand-relocated `harny-feedback-web.yml` and keeping the generated
  `harny-feedback-apps-web.yml`; a green CI run against the refactor is still
  pending.

### Run the web feed locally

```bash
cd apps/web
npm install                 # first time only
cp .env.example .env.local  # already points at the real deployed feed-api
npm run dev                 # http://localhost:3000
```

Expect: the real curated feed (currently ~87 cards) server-rendered on first
load — no loading spinner, no empty shell. Click a tag chip → the URL becomes
`/?tag=<x>` and the page re-renders with a real new `GET /v1/cards?tag=<x>`
request (not a client-side filter). "Next page →" advances via `?cursor=`;
browser Back returns to the previous page for free (there is no "Previous"
link by design — AD-5). `http://localhost:3000/?tag=zzz-no-such-tag` exercises
the AD-6 drain and renders the `feed-no-match` state, not a blank page.
`http://localhost:3000` already works out of the box against the real API: it
is the one origin `feed-api`'s CORS allow-list permits today (though CORS
itself is not exercised by this app — see AD-4 — since `next dev`'s fetch is
server-side).

To exercise the `feed-error` state locally, temporarily point at an
unreachable host and reload:

```bash
FEED_API_BASE_URL=http://127.0.0.1:9 npm run dev
```

To run the offline end-to-end suite (Playwright, local `feed-api` stub, no AWS
requests; needs the Chromium browser installed once via
`npx playwright install chromium`):

```bash
npm run test:e2e
```

### Deploying `web-feed-ui` (manual runbook — human-run only, AD-10)

No agent may run any command in this section — `vercel*`, `cdk deploy`, or
`cdk destroy`. This is a transcription of `apps/web/specs/archived/web-feed-ui/roadmap.md`
Phase 5, with `<placeholders>` for the values only an actual deploy can
produce. Record the real values here (and in
`apps/web/specs/archived/web-feed-ui/audit.md`'s `M*` rows) once run.

1. **Create the Vercel project.**
   - Import the repository at <https://vercel.com/new>.
   - **Root Directory: `apps/web`** — the one setting that must not be left
     at the repo root.
   - Framework preset: Next.js (auto-detected); build/install commands: leave
     as detected (`next build` / `npm install`).
   - Environment Variables → Production (and Preview, if wanted):
     `FEED_API_BASE_URL = https://25p45q6m6f.execute-api.us-east-1.amazonaws.com`
     — **no** `NEXT_PUBLIC_` prefix (server-only by design, AD-4).
   - Deploy. Record the production URL: `https://<project>.vercel.app`.
   - CLI alternative: `npm i -g vercel && vercel link && vercel env add
     FEED_API_BASE_URL production && vercel --prod`, run from `apps/web/`.
2. **Browser-verify the deployed URL:** real cards, ordered by relevance then
   date; a tag chip narrows the feed and the URL becomes `/?tag=<x>`; "Next
   page →" shows cards absent from page 1 (spot-check two `card_id`s/titles
   for disjointness); `/?tag=zzz-no-such-tag` renders the no-match state, not
   a blank page.
3. **Update `feed-api`'s CORS allow-list** (this is why it waits until now —
   it needs the real origin):
   ```bash
   uv sync --group infra
   uv run cdk deploy --app "python infra/app.py" AiRadarFeedApi \
     -c feed_api_allowed_origins="http://localhost:3000,https://<project>.vercel.app" \
     -c feed_api_reserved_concurrency=none   # ONLY if AWS Support case
                                              # 178836416700301 is still open
                                              # — see specs/feed-api/tasks.md 6.2
   ```
   Run `uv run cdk diff --app "python infra/app.py" AiRadarFeedApi` first and
   confirm the **only** change is `CorsConfiguration.AllowOrigins`. (Durable
   alternative: edit `DEFAULT_ALLOWED_ORIGINS` in `infra/lib/feed_api.py` and
   the origin assertion in `tests/test_infra_feed_api.py`, then deploy with
   no `-c` override.)
4. **Verify CORS by curl, both halves:**
   ```bash
   API=https://25p45q6m6f.execute-api.us-east-1.amazonaws.com
   curl -si -H "Origin: https://<project>.vercel.app" "$API/v1/cards?limit=1" \
     | grep -i access-control-allow-origin      # EXPECT: the Vercel origin
   curl -si -H "Origin: https://evil.example.com" "$API/v1/cards?limit=1" \
     | grep -i access-control                   # EXPECT: no output at all
   ```
5. **Record the real values here and in `apps/web/specs/archived/web-feed-ui/audit.md`**: the
   Vercel URL, the origin now allow-listed, the deploy date, and the teardown
   steps (delete the Vercel project; redeploy `AiRadarFeedApi` with the
   origin list back to `http://localhost:3000`).

**Teardown, if ever needed:** delete the Vercel project from its dashboard
(free tier, no AWS resource involved); revert `feed-api`'s CORS allow-list to
`http://localhost:3000` with the same `cdk deploy -c feed_api_allowed_origins=...`
pattern above.

## Phase 3 — Chatbot (2 specs shipped: `chat-retrieval`, `chat-agent-runtime`; chat agent deployed)

Phase 3 turns the curated cards into a RAG chatbot. Its first spec,
[`chat-retrieval`](specs/archived/chat-retrieval/), is the **retrieval half**: every
card gets a stored embedding, and Plane B can rank those vectors against a question.
Its second, [`chat-agent-runtime`](specs/archived/chat-agent-runtime/), runs that chat as
its own stateless agent on AgentCore Runtime (live since 2026-10-18). The chat API
(throttling, public URL) and the web chat UI are later Phase 3 specs and are not started.

| Spec | Status | What it added |
|---|---|---|
| [`chat-retrieval`](specs/archived/chat-retrieval/) | ✅ Implemented, audit APPROVED WITH RESERVATIONS (round 3); **deployed 2026-10-18** (runbook steps 2–4) | Curation-time Titan v2 embeddings on the DynamoDB `embedding` attribute, a backfill command, a DynamoDB retriever in `src/chat/`, and a `run_chat.py` backend switch. Shipped 2026-10-13. Details below. |
| [`chat-agent-runtime`](specs/archived/chat-agent-runtime/) | ✅ Shipped & live-verified (AC10 human-run 2026-10-18); audit APPROVED WITH RESERVATIONS (round 3) | The RAG chat as a second AgentCore Runtime agent (`ai_radar_chat`): a stateless `{question, history}` → `{answer, sources}` entrypoint (`chat_app.py`), a LangGraph retrieve-then-answer graph, request validation and caps, its own least-privilege role (`AiRadarChatRuntime`), and the default chat model moved to Sonnet 4.6. Details in "chat-agent-runtime" below. |

> **What is deployed now.** The curation agent image was rebuilt, so new cards carry an
> embedding. The backfill has run, and all 16 live cards have one. `AiRadarRuntimeRole`
> carries the Titan grant. The chat agent runs as `ai_radar_chat-JFCO0R9lkT`, and its role
> is the `AiRadarChatRuntime` stack. The chat path is not yet reachable from the public
> feed. The curation schedule stays `DISABLED`. The local `run_chat.py` path is unchanged.
> See "Account migration (2026-10-05)" for the live state.

### What shipped

- **Curation-time embeddings.** `build_graph(store, discoverer, embedding_writer=…)`
  (`src/curation/graph.py`) adds an `embed` node after `persist`, only when a writer is
  passed. `runtime_app.py` passes its `DynamoCardStore`; `run_curation.py` passes it
  when `CARD_STORE_BACKEND=dynamo`. Each persisted card is embedded from
  `card_text(card)` (the same text Phase 0 embedded) with Titan v2, `EMBED_DIM` floats,
  normalized. Vectors are written by `DynamoCardStore.set_embeddings`, a conditional
  `update_item` that never creates an item. `upsert` still never writes `embedding`
  (card-persistence PS-2), and a re-upsert leaves a vector intact.
- **Embedding never fails a run.** A Titan failure on one card leaves that card persisted
  without a vector. The counts `embedded` and `embed_failed` go into the run's state and
  the `embed_complete` log record. `RunSummary` and the EMF metrics are unchanged.
- **Backfill.** `uv run run_backfill_embeddings.py` embeds every card with no vector, or
  with a vector whose length is not `EMBED_DIM`. It prints the account id and table name
  first, then `embedded=N skipped=N failed=N`. It is idempotent: a second run prints
  `embedded=0`. It uses your local AWS credentials. Logic is in `src/curation/backfill.py`.
- **Plane B retriever.** `DynamoCardRetriever` (`src/chat/retriever.py`) runs a paginated
  `Query` on the `feed-by-score` index (partition `CARD`), never a `Scan`. It ranks the
  stored vectors by dot product against the query vector (cosine, since both are
  normalized), returns the top `k` as `(card_dict, score)` pairs, and strips the vector
  from each card. Un-embedded and wrong-length cards are excluded.
- **`RagChat(retriever, k)`.** `src/shared/chat.py` takes a `Retriever` Protocol. The
  in-memory `CardIndex` and `DynamoCardRetriever` both satisfy it.
- **`run_chat.py` switch (AC7, offline).** The default is `CARD_STORE_BACKEND=json`, which
  is the Phase 0 behavior. `CARD_STORE_BACKEND=dynamo` answers from DynamoDB-retrieved
  cards with `[n]` citations.
- **Infra (deployed 2026-10-18).** `infra/lib/agent_runtime.py` adds an `InvokeTitanEmbed`
  statement, `bedrock:InvokeModel` on the Titan v2 foundation-model ARN only. The Haiku
  statement stays Haiku-only. The retriever's `dynamodb:Query` grant lives in the chat
  agent's own role (`AiRadarChatRuntime`, see `chat-agent-runtime`), not the curation role.

Test status (offline, Bedrock stubbed, DynamoDB via moto): `uv run pytest tests/` →
406 passed (baseline 350); `uv run ruff check` clean; `uv run mypy .` clean (78 files).
Two existing tests were edited: the `_fake_build_graph` helper gained an
`embedding_writer` parameter, and the "no titan" assertion in
`tests/test_infra_agent_runtime.py` now covers only the Haiku statement. One assertion
line in `tests/test_config.py` was removed for audit finding F3 (the `EMBED_MODEL_ID`
re-export), with human approval.

### Deploy record (done 2026-10-18, in this order)

1. **Redeployed the `AiRadarRuntimeRole` stack.** Added the Titan v2 `InvokeModel`
   grant (`InvokeTitanEmbed`). Account `626259825216`, `UPDATE_COMPLETE`.
2. **Rebuilt and redeployed the curation agent image** (`agentcore deploy -a ai_radar_curation`).
   One curation pass embedded its cards (`embed_complete`: embedded 8, embed_failed 0).
3. **Ran the backfill once against the live table.** First run `embedded=8 skipped=8
   failed=0`; second run `embedded=0 skipped=16 failed=0`. The live table has 16 of 16
   cards with an `embedding`.

The chat agent's live turns (steps 6 and 7 below) exercise the same `DynamoCardRetriever`
against the live table. The `CARD_STORE_BACKEND=dynamo uv run run_chat.py` check from
"Not verified live" below has still not been run.

### chat-agent-runtime — what shipped

- **Entrypoint.** `chat_app.py` at the repo root, the only file that imports
  `bedrock_agentcore` for chat. Its `@app.entrypoint` handler is synchronous: it takes
  `{"question": str, "history": [...]}` and returns `{"answer": str, "sources": [...]}`.
  Each source has `n`, `title`, `url`, `source`, `published` (may be `null`) and `score`
  (rounded to 4 places), and never a vector. Failures return `{"error": "invalid_request",
  "detail": "<rule>"}` or `{"error": "upstream_failure"}`.
- **Stateless.** The caller holds the history. The graph is compiled without a checkpointer,
  and nothing from one invocation reaches the next.
- **Validation before any AWS call** (`src/chat/request.py`, pure). The caps are typed
  pydantic-settings fields in `src/chat/config.py`: `CHAT_MAX_QUESTION_CHARS` (1000),
  `CHAT_MAX_HISTORY_TURNS` (10, so at most 20 items), and `CHAT_MAX_HISTORY_ITEM_CHARS`
  (4000). History roles must alternate and end with `assistant`.
- **Graph** (`src/chat/graph.py`, portable and infra-free): `retrieve` (through the
  existing `Retriever` Protocol, which `DynamoCardRetriever` satisfies), then `answer`.
  With no hits, `answer` returns a fixed "not in the collected news" message with
  `sources: []` and makes **no model call**.
- **Shared answer step.** `answer_question` in `src/shared/chat.py` holds the Phase 0 prompt,
  context block, `[n]` numbering and Sonnet call. `RagChat.ask` delegates to it, so
  `run_chat.py` and the agent produce identical model requests.
- **Chat model: Sonnet 4.6.** The `SONNET_MODEL_ID` default is now
  `us.anthropic.claude-sonnet-4-6` (it was Sonnet 4.5, now `LEGACY` in Bedrock). An env
  override still wins. The Haiku default and the curation graph are unchanged.
- **Logs.** One `chat_turn` record per invocation, from the child logger
  `bedrock_agentcore.app.chat`, with `question_chars`, `history_items`, `hits`,
  `retrieval_ms`, `model_ms` and `outcome` (`ok`, `no_context`, `invalid_request`,
  `upstream_failure`). It never carries question, history or answer text.
- **Infra.** `AiRadarChatRuntime` (`infra/stacks/chat_runtime_stack.py`, construct in
  `infra/lib/chat_runtime.py`) creates a separate execution role with exactly seven
  statements: Sonnet 4.6 invoke (profile plus three foundation-model ARNs), Titan v2
  invoke, `dynamodb:Query` on the `feed-by-score` index only, AgentCore logs, and ECR
  pull. The trust policy allows only `bedrock-agentcore.amazonaws.com`, conditioned on
  `aws:SourceAccount` and `aws:SourceArn`. The curation role is not widened, and the
  chat role has no secret grant.
- **Packaging.** There is still one root `Dockerfile`, with
  `CMD ["sh", "-c", "exec python \"${AGENT_ENTRYPOINT:-runtime_app.py}\""]`. The default
  keeps the curation agent unchanged. The chat agent sets `AGENT_ENTRYPOINT=chat_app.py`
  at deploy time, which gives each agent its own image and Runtime. The toolkit builds only
  the `Dockerfile` at the agent's `source_path`, which is why there is one shared file.
  The ARM64 image builds, and `import chat_app` succeeds inside it with no region env.
- **Test status (offline, 2026-10-18):** `uv run pytest tests/` gives 487 passed;
  `uv run ruff check`, `uv run ruff check --isolated` and `uv run mypy .` are clean (87
  files). Audit: APPROVED WITH RESERVATIONS (round 3). Reservations: F11 (one latency sample,
  see Live results). Open LOW findings: F5 (a mislabeled test param), F6 (plan `-k`
  selectors that miss tests), F7 (partial timings lost on `upstream_failure`) and F8 (CI
  not yet run on a PR). None of them hides an unmet AC.

### Chat agent runbook (`chat-agent-runtime`, AC10 — human-run, one step at a time)

All eight steps were human-run on 2026-10-18 in account `626259825216` (table
`ai-radar-cards`). The results are recorded under "Live results" below. The steps stay
here as the procedure for a redeploy. Each writes to the real account, so run them one
at a time and print the account first (`aws sts get-caller-identity`).

1. **Smoke call on Sonnet 4.6** with the real request shape (`cachePoint` +
   `temperature`): `aws sts get-caller-identity && SONNET_MODEL_ID=us.anthropic.claude-sonnet-4-6 PYTHONPATH=src uv run python -c "from shared.config import SONNET_MODEL_ID; print('model:', SONNET_MODEL_ID); from shared.chat import answer_question; print(answer_question('ping', [], [({'title':'t','source':'s','summary':'x','url':'u'}, 1.0)]))"`
   (the account prints first; `PYTHONPATH=src` puts `shared` on the path; the explicit `SONNET_MODEL_ID` plus the printed `model:` line guard against a local `.env` still pinning Sonnet 4.5, which `load_dotenv()` would otherwise honor, so confirm it prints `us.anthropic.claude-sonnet-4-6`).
   If Bedrock rejects the `cachePoint`, record it as an audit finding.
2. `cd infra && cdk deploy AiRadarRuntimeRole` (adds the Titan grant).
3. Rebuild/redeploy the curation image (`agentcore deploy -a ai_radar_curation`),
   run one curation pass, confirm new cards carry an `embedding`.
4. `uv run run_backfill_embeddings.py` once (second run prints `embedded=0`).
5. Deploy the chat role and agent. **The `--env AGENT_ENTRYPOINT=chat_app.py`
   flag is mandatory**, otherwise the shared image starts the curation entrypoint:

   ```bash
   cd infra && cdk deploy AiRadarChatRuntime      # note ExecutionRoleArn
   agentcore configure --create -n ai_radar_chat -e chat_app.py \
     -er <ChatExecutionRoleArn> -r us-east-1 -ecr auto --disable-memory --non-interactive
   agentcore deploy -a ai_radar_chat --env AGENT_ENTRYPOINT=chat_app.py
   ```

   Configuring a second agent can change `default_agent` in
   `.bedrock_agentcore.yaml` (gitignored local state), so always pass
   `-a <agent>` to `deploy`, `invoke`, `status` and `destroy`.
6. Invoke with a real question; expect `answer` plus `sources` that exist in
   `ai-radar-cards`:
   `agentcore invoke -a ai_radar_chat '{"question": "What shipped this week?", "history": []}'`
7. Invoke with an invalid request; expect `{"error": "invalid_request", "detail": ...}`:
   `agentcore invoke -a ai_radar_chat '{"question": ""}'`
8. Record `retrieval_ms` (from the `chat_turn` log records) and the live card
   count against the ADR 0009 ceiling (~2,000 cards / p95 ~1 s).

#### Live results (2026-10-18)

| Step | Result |
|---|---|
| 1. Sonnet 4.6 smoke call | Printed `model: us.anthropic.claude-sonnet-4-6`. Bedrock accepted the `cachePoint` and `temperature` request shape and returned a normal answer. The open question in the intent is closed, with no rejection. |
| 2. `AiRadarRuntimeRole` redeploy | `cdk diff` showed one added statement (`InvokeTitanEmbed`). `UPDATE_COMPLETE` in 23.6 s. |
| 3. Curation image redeploy and pass | Run `a6168787ff1c4165a223d4e6ef26c91c`: discovered 40, summarized 8, persisted 8, store_failures 0, 30.6 s, est. cost $0.06. `embed_complete`: embedded 8, embed_failed 0. Cards went from 8 to 16. |
| 4. Backfill | Account and table printed first. `embedded=8 skipped=8 failed=0`, then `embedded=0 skipped=16 failed=0`. 16 of 16 cards carry an `embedding`. |
| 5. Chat role and agent | `AiRadarChatRuntime` `CREATE_COMPLETE` in 39 s. The role has the seven AC7 statements and nothing else. The agent runtime is `ai_radar_chat-JFCO0R9lkT`. Its `chat_turn` records are in the `/aws/bedrock-agentcore/runtimes/ai_radar_chat-JFCO0R9lkT-DEFAULT` log group. |
| 6. Real question | `What are the latest developments in open-weight models?` returned a cited answer with `[1]`–`[3]` and 4 sources numbered 1–4 (`n,title,url,source,published,score` only). All 4 source URLs exist in `ai-radar-cards`. The `chat_turn` record shows `question_chars 55, history_items 0, hits 4, retrieval_ms 330, model_ms 3304, outcome ok`. The record has no question or answer text. |
| 7. Invalid request | `{"error": "invalid_request", "detail": "question_empty"}`. The `chat_turn` record shows `question_chars 0, hits 0, retrieval_ms 0, model_ms 0, outcome invalid_request`, so no retrieval or model call was made. The chat log group has zero `chat_turn_failed` records. |
| 8. Latency and card count | **16 live cards** (0.8% of the ~2,000-card ceiling) and **one** measured `retrieval_ms` sample, 330 ms (this includes the Titan embed call). No p95 can be computed from one sample. The human closed the step on this provisional evidence. It is a recorded reservation, not a failure. See "Known limitation (F11, accepted)" below. |

**`default_agent` note.** Configuring the second agent changed `default_agent` in
`.bedrock_agentcore.yaml` (gitignored local state) to `ai_radar_chat`. A bare
`agentcore deploy`, `invoke`, `status` or `destroy` now targets the chat agent. Always
pass `-a ai_radar_curation` or `-a ai_radar_chat` explicitly.

**Still open after this spec:** a p95 retrieval latency over enough real turns, recorded
against the ADR 0009 ceiling, once the corpus or traffic grows. The chat turn latency
(`model_ms`) is about 3.3 s on one sample, which is not a p95 either. Also open, all LOW
and non-blocking: `upstream_failure` records report `hits=0` and `retrieval_ms=0` even
when retrieval succeeded (the partial timing is lost, audit F7). CI on the PR (`harny-feedback.yml`)
runs only after this branch is pushed (audit F8).

**Teardown gotcha:** `agentcore destroy` deletes any role in the config's
`aws.execution_role`, including the CDK-owned one. Null that field in
`.bedrock_agentcore.yaml` for the chat agent before `agentcore destroy -a ai_radar_chat`.

### Not verified live

These are **not** verified live:

- A live `CARD_STORE_BACKEND=dynamo uv run run_chat.py` run against real DynamoDB and
  Bedrock. The chat agent's live turns use the same retriever, but the local script was
  not run.
- CI on this branch: the branch is unpushed, so no `harny-feedback.yml` run exists.
- Evidence that the Stop hook fired (audit finding F7, open, LOW, from `chat-retrieval`).

### Known limitation (F11, accepted)

A card whose `upsert` fails still gets a Titan call. Its conditional vector write then
fails and the card is counted in `embed_failed`, so AC2 holds. The cost is one small
Titan call per failed upsert, which the auditor estimated at about $0.00002 per card
(not checked against current pricing).

### Scale ceiling for brute force

The retriever is brute force on purpose: no vector database, roughly $0 extra. Revisit
this choice at about **2,000 embedded cards**, or when a measured p95 retrieval latency
rises above about **1 s**. As of 2026-10-18 the live corpus is 16 embedded cards, and one
live chat turn measured `retrieval_ms=330`. That is a single sample, not a p95 (see
"chat-agent-runtime" above). The first remedy is an in-process TTL cache in the
long-lived chat runtime. It is **not** implemented; `chat-agent-runtime` did not add it,
and the measurement informs a later decision without triggering one. The second is
pgvector or Aurora, per the design doc's §7. At the current cap of 8 new cards per run,
2,000 cards is about eight months of daily runs.

## Account migration (2026-10-05)

The whole backend was redeployed into a second AWS account, **`626259825216`**
(IAM user `daniele`, `us-east-1`), from scratch — no data was migrated, so
`ai-radar-cards` started empty. This is the **current live state**; the
original account (`536697225154`) is no longer the deploy target.

**Deployed and verified (2026-10-05/06):** `CDKToolkit` (bootstrap) plus
`AiRadarCardStore`, `AiRadarRuntimeRole`, `AiRadarSchedule` (`DISABLED`),
`AiRadarBudget` and `AiRadarFeedApi`, and the `ai_radar_curation` agent runtime
(`ai_radar_curation-FW1w976PCI`, `READY`; its ARN is in SSM
`/ai-radar/agent-runtime-arn`). A smoke `agentcore invoke '{}'` acked
immediately and the `curation_run_complete` record showed `discovered: 30`,
`persisted: 8` in 26.9s; the table went 0 → 8. `GET /v1/cards` returned those
cards, an out-of-range `limit` returned 400, and CORS allowed only
`http://localhost:3000`. New feed API URL: `https://25p45q6m6f.execute-api.us-east-1.amazonaws.com`.

**Changed since, 2026-10-18 (`chat-retrieval` and `chat-agent-runtime` deploys, account
`626259825216`):**

- `AiRadarRuntimeRole` was redeployed for the Titan v2 grant (`InvokeTitanEmbed`).
- The `ai_radar_curation` agent image was rebuilt and redeployed, and its runtime embeds
  each persisted card. The backfill then embedded the 8 older cards, so all 16 live cards
  carry an `embedding`.
- New stack **`AiRadarChatRuntime`** (`CREATE_COMPLETE`): the chat execution role
  (`ChatRuntimeExecutionRole…`, seven statements, see "chat-agent-runtime" above).
- New agent runtime **`ai_radar_chat-JFCO0R9lkT`** (`ai_radar_chat`, `-DEFAULT` endpoint),
  deployed with `--env AGENT_ENTRYPOINT=chat_app.py`, from the same root `Dockerfile` as the
  curation agent.
- `default_agent` in the local `.bedrock_agentcore.yaml` now points at `ai_radar_chat`
  (see the `default_agent` note under the chat runbook's live results).
- The curation schedule stays **`DISABLED`**, and no teardown happened.
- Nothing from the Phase 3 chat path is exposed publicly yet. There is no chat API or
  throttling until `chat-api`. Invocation needs IAM credentials.

**What had to change for a new account**

- **The account is pinned as a literal in code.** `infra/lib/agent_runtime.py`
  and `infra/lib/feed_api.py` default `account=` to `626259825216` (and their
  tests assert it). Redeploying to yet another account means changing both
  files and `tests/test_infra_agent_runtime.py` / `tests/test_infra_feed_api.py`;
  forgetting is silent — CDK builds IAM policies pointing at the other account's
  resources and the failure only shows up as `AccessDenied` at runtime. Run
  `cdk diff` and grep it for the old account ID before deploying.
- **Regenerate `.bedrock_agentcore.yaml`** (gitignored, holds the old account's
  role, ECR and agent ARN): move it and `.bedrock_agentcore/` aside, then
  `agentcore configure --create ... -er <ExecutionRoleArn>` as in the runbook.
- **Lambda concurrency quota is 10** in this account, same as the original, so
  `AiRadarFeedApi` fails with "decreases account's UnreservedConcurrentExecution
  below its minimum value of [10]". Deploy it with
  `-c feed_api_reserved_concurrency=none` (every time, until the quota is
  raised). API Gateway throttling (20 rps / burst 40) still applies. A failed
  first create leaves a `ROLLBACK_COMPLETE` stack that must be deleted before
  retrying.
- **Budget limit is $500** here, set with `-c budget_limit_usd=500` (the code
  default is still $250); a later deploy without the flag reverts it. Thresholds
  stay at $50/$100/$250. The SNS email subscription must be confirmed by hand.
- The Tavily key is seeded manually with `aws secretsmanager put-secret-value`
  (never via CDK or the image).

**Still open:** point `apps/web`'s `FEED_API_BASE_URL` (Vercel env var) and the
feed API's CORS allow-list at the new deployment; tear down or leave the old
account's stacks as you see fit (note the `agentcore destroy` role gotcha above).

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

### Mini RAG chat (Plane B preview, local path)

`uv run run_chat.py` runs a grounded chatbot over the curated cards. This is the
default local path (`CARD_STORE_BACKEND=json`, reading `.ai_radar_cache/cards.json`).
The DynamoDB retriever that `chat-retrieval` added is opt-in; see "Phase 3 — Chatbot" below.

| Step | Where | Notes |
|---|---|---|
| Embed cards | `src/shared/embeddings.py` (called from `src/shared/retrieval.py`) | Titan v2 embeddings, cached in `.ai_radar_cache/embeddings.json`. |
| Retrieve | `src/shared/retrieval.py` (`CardIndex`) | In-memory cosine top-k (normalized → dot product). Satisfies the `Retriever` Protocol in `src/shared/chat.py`. |
| Answer | `src/shared/chat.py` | `RagChat(retriever, k)`: Sonnet, grounded in retrieved cards, inline `[n]` citations, multi-turn memory. |

It answers only from retrieved cards (no hallucination) and says so when the corpus
lacks the answer. The stable system prompt uses a Bedrock prompt-cache point.

### Deliberately deferred (superseded by Phase 1 progress above, or still later)

- ~~**Search API** (Tavily/Exa)~~ — done, see `tavily-discovery` above.
- ~~**LangGraph orchestration**~~ — done, see `curation-graph` above.
- ~~**DynamoDB card persistence**~~ — done, see `dynamodb-card-store` above. The `embedding` attribute it reserved is now populated by `chat-retrieval` (Phase 3); a real vector store is still deferred (see "Phase 3 — Chatbot" for the scale ceiling).
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

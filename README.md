# AI Radar

AI-news curation feed + RAG chatbot. See [`docs/app-design-on-agentcore.md`](docs/app-design-on-agentcore.md) for the full design.

## Phase 1 — Curation MVP (in progress)

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
| [`runtime-packaging`](specs/runtime-packaging/) | ✅ Shipped & deploy-verified | Wraps the unchanged graph in a `BedrockAgentCoreApp` entrypoint (`runtime_app.py`), a least-privilege execution-role + Tavily-secret CDK stack (`infra/lib/agent_runtime.py`), and a `uv`-based Dockerfile. Deployed for real on 2026-07-28 (real Tavily key, cards landed in `ai-radar-cards`, teardown verified clean) — see the runbook below. Currently torn down between runs; nothing billing until the next deploy. |
| `eventbridge-schedule` | ⏳ Not started | Daily automated trigger. |
| `run-observability` | ⏳ Not started | Structured run-summary logging. |

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

Output still lands in `.spike_cache/cards.json` / `seen.json` by default (unchanged
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

```bash
agentcore invoke '{}'
aws dynamodb scan --table-name ai-radar-cards --select COUNT
agentcore invoke '{}'   # re-invoke
```

Verified 2026-07-28: first invoke returned
`{"discovered": 50, "summarized": 8, "persisted": 8, "tavily_enabled": true}`
and the table went 0 → 8. Re-invoking is **not** a no-op: `deduped` dropped
50 → 42 (the 8 already-stored cards were correctly excluded — dedup works),
but the table still grew to 16, because `SPIKE_MAX_ITEMS=8` caps how many
*new* items get summarized per run — a re-invoke picks up the next batch of
previously-undiscovered items rather than repeating the first one. That's the
intended incremental-curation shape (each scheduled run adds a bounded
slice), not a dedup bug. True idempotency only shows up once the discoverer
stops returning new candidates.

**Re-target without a rebuild**: the same image reads `CARD_TABLE_NAME`,
`AWS_REGION`, `SPIKE_MAX_ITEMS`, `SPIKE_PER_FEED`, `CURATION_TAVILY_*`, and
`TAVILY_SECRET_NAME` from env — set them via `agentcore configure --env
KEY=VALUE` (or a redeploy of just the config) to point at a dev table with no
image rebuild.

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

### Tests

```bash
uv run pytest tests/ -v   # 67 tests, all offline (Bedrock/Tavily stubbed, DynamoDB via moto, CDK via synth-only assertions, AgentCore handler mocked)
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
uv run run_spike.py           # curation loop (skips already-seen items)
uv run run_spike.py --force   # re-summarize everything
uv run run_chat.py            # ask questions about the curated cards (RAG)
```

AWS credentials are read from `~/.aws` by default; copy `.env.example` → `.env` only to
override region/models. Requires Bedrock model access to Claude Haiku 4.5, a Sonnet
chat model, and Titan Embeddings v2 in your region.

### What it does

| Step | Where | Notes |
|---|---|---|
| Discover | `src/spike/feeds.py` | Pulls recent entries from curated AI/ML RSS feeds (no API key). |
| Dedup | `src/spike/pipeline.py` | URL-hash cache in `.spike_cache/seen.json` → idempotent re-runs. |
| Summarize + tag | `src/spike/bedrock.py` | Bedrock Converse with a **forced tool call** → guaranteed structured cards. |
| Rank + render | `src/spike/cards.py` | Sort by model relevance score; pretty console panels. |

Output is also written to `.spike_cache/cards.json` for inspection.

### Mini RAG chat (Plane B preview)

`uv run run_chat.py` runs a grounded chatbot over the curated cards:

| Step | Where | Notes |
|---|---|---|
| Embed cards | `src/spike/retrieval.py` | Titan v2 embeddings, cached in `.spike_cache/embeddings.json`. |
| Retrieve | `src/spike/retrieval.py` | In-memory cosine top-k (normalized → dot product). |
| Answer | `src/spike/chat.py` | Sonnet, grounded in retrieved cards, inline `[n]` citations, multi-turn memory. |

It answers only from retrieved cards (no hallucination) and says so when the corpus
lacks the answer. The stable system prompt uses a Bedrock prompt-cache point.

### Deliberately deferred (superseded by Phase 1 progress above, or still later)

- ~~**Search API** (Tavily/Exa)~~ — done, see `tavily-discovery` above.
- ~~**LangGraph orchestration**~~ — done, see `curation-graph` above.
- ~~**DynamoDB card persistence**~~ — done, see `dynamodb-card-store` above. A real vector store for RAG (Phase 3) is still deferred — the table reserves an unpopulated `embedding` attribute for it.
- ~~**AgentCore Runtime packaging**~~ — done and deploy-verified, see `runtime-packaging` above. Torn down between runs until `eventbridge-schedule` gives it a reason to stay up.
- **EventBridge scheduling** — daily automated trigger of the deployed agent (`eventbridge-schedule`, not started).
- **AgentCore Memory** — chat memory is an in-process list; becomes AgentCore Memory (STM/LTM) in a later phase (Plane B, untouched by Phase 1).

### Config knobs (`.env` or env vars)

`AWS_REGION`, `HAIKU_MODEL_ID`, `SPIKE_MAX_ITEMS`, `SPIKE_PER_FEED` — see `.env.example`.

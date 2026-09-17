# Contract: runtime-packaging

> **Language & layout.** Runtime code is Python 3.11+ (`uv`, `src/` layout,
> `[tool.uv] package = false`). Infra is AWS CDK v2 in **Python**
> (`aws-cdk-lib`, `constructs`), under `infra/`, following the Spec 03
> construct → stack → app pattern. The container is defined by a root
> `Dockerfile`. This spec **adds** a root entrypoint (`runtime_app.py`), one
> new config knob in `src/curation/config.py`, one new CDK construct + stack,
> and container/CLI plumbing. It **imports, never forks** Specs 01–03: the
> compiled graph, `DynamoCardStore`, `CompositeDiscoverer`, `RssDiscoverer`,
> `TavilyDiscoverer`. **No file under `src/curation/{graph,nodes,state,
> interfaces}.py` is modified** (portability guarantee).

## AWS / library API surface (pinned via Context7 + AWS docs — do not trust memory)

Verified 2026-07. Sources: `bedrock-agentcore` SDK
(`/aws/bedrock-agentcore-sdk-python`), starter toolkit
(`/aws/bedrock-agentcore-starter-toolkit`, `documentation/docs/user-guide/
runtime/{quickstart,overview,permissions}.md`), AWS Bedrock geographic
cross-Region inference IAM docs.

### `bedrock-agentcore` SDK — entrypoint

```python
from bedrock_agentcore import BedrockAgentCoreApp   # also re-exported as bedrock_agentcore.runtime.BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.entrypoint
def handler(payload):          # sync callable; receives the parsed request body (a dict)
    ...
    return {"...": "..."}      # return value is serialized back to the invoker

app.run()                      # starts the HTTP server (port 8080, /invocations + /ping)
```

- The decorator registers a **callable** entrypoint (custom-agent form). A sync
  function that **returns** a value is valid (non-streaming path); the return
  value is what `agentcore invoke` / an EventBridge trigger receives back.
- `payload` is the parsed JSON request body. This spec's handler **accepts but
  ignores** it — all config is env-driven (Spec 05 invokes with `{}`).
- `app.run()` must run only when executed as the container process, **not** on
  import (guarded by `if __name__ == "__main__":`) so the pytest unit test can
  `import runtime_app` without starting a server.

### `agentcore` CLI (starter toolkit)

```bash
# Configure with an EXISTING custom execution role (do NOT let the toolkit
# auto-create one). Deps auto-detected from pyproject.toml (no requirements.txt).
agentcore configure -e runtime_app.py --execution-role <ROLE_ARN> [--non-interactive]

# Build (ARM64) + push to ECR + create the Runtime agent.
agentcore launch                 # `agentcore deploy` is the documented equivalent

# Inspect status / agent id / log group.
agentcore status

# Invoke the deployed agent (empty payload — config is env-driven).
agentcore invoke '{}'

# Tear down toolkit-created resources (Runtime endpoint, ECR image/repo, and any
# toolkit-created IAM — our custom role/secret live in CDK and are destroyed separately).
agentcore destroy
```

- `configure` writes a `.bedrock_agentcore.yaml` (agent name, region,
  entrypoint, role ARN, ECR repo) — committed to the repo for reproducibility;
  it contains **no secrets**.
- Env vars for the container are set at configure/launch time (verify exact flag
  — `--env KEY=VALUE` — during implementation; `.bedrock_agentcore.yaml` also
  carries them). The Tavily **key** is never among them; only the secret **name**.
- Dependency detection: the toolkit finds `pyproject.toml` (type `pyproject`).
  Because the repo is `uv`-managed with a `src/` layout and `package = false`,
  the **generated Dockerfile's dependency step is adapted to `uv sync --frozen`**
  and the final Dockerfile is committed (see Data Models → Dockerfile).

### AgentCore Runtime execution-role — trust policy (pinned)

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AssumeFromAgentCore",
    "Effect": "Allow",
    "Principal": { "Service": "bedrock-agentcore.amazonaws.com" },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": { "aws:SourceAccount": "536697225154" },
      "ArnLike": { "aws:SourceArn": "arn:aws:bedrock-agentcore:us-east-1:536697225154:*" }
    }
  }]
}
```

### AgentCore Runtime execution-role — permissions policy (pinned, least-privilege)

Account `536697225154`, source region `us-east-1`. Haiku profile
`us.anthropic.claude-haiku-4-5-20251001-v1:0`; its bare foundation-model id is
`anthropic.claude-haiku-4-5-20251001-v1:0`. **The exact member regions of the
`us.` profile MUST be verified at deploy time** via
`aws bedrock get-inference-profile --inference-profile-identifier
us.anthropic.claude-haiku-4-5-20251001-v1:0`; the geographic `us` profile
routes to `us-east-1`, `us-east-2`, `us-west-2` (default assumption below).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeHaikuCrossRegion",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": [
        "arn:aws:bedrock:us-east-1:536697225154:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0"
      ]
    },
    {
      "Sid": "CardStoreReadWrite",
      "Effect": "Allow",
      "Action": ["dynamodb:BatchGetItem", "dynamodb:UpdateItem"],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:536697225154:table/ai-radar-cards",
        "arn:aws:dynamodb:us-east-1:536697225154:table/ai-radar-cards/index/feed-by-score"
      ]
    },
    {
      "Sid": "TavilyKeyRead",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:us-east-1:536697225154:secret:ai-radar/tavily-api-key-*"
    },
    {
      "Sid": "AgentCoreLogsWrite",
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"],
      "Resource": [
        "arn:aws:logs:us-east-1:536697225154:log-group:/aws/bedrock-agentcore/runtimes/*",
        "arn:aws:logs:us-east-1:536697225154:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
      ]
    },
    {
      "Sid": "AgentCoreLogsDescribe",
      "Effect": "Allow",
      "Action": "logs:DescribeLogGroups",
      "Resource": "arn:aws:logs:us-east-1:536697225154:log-group:*"
    },
    {
      "Sid": "EcrImagePull",
      "Effect": "Allow",
      "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
      "Resource": "arn:aws:ecr:us-east-1:536697225154:repository/bedrock-agentcore-*"
    },
    {
      "Sid": "EcrAuthToken",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    }
  ]
}
```

> **Scoping rationale (pin for the auditor):**
> - **Bedrock** — Converse (used by `spike.bedrock.summarize`) is authorized by
>   `bedrock:InvokeModel`. Cross-region inference requires **both** the
>   source-region inference-profile ARN **and** the bare foundation-model ARN in
>   the source + every destination region (verified AWS requirement). Streaming
>   (`InvokeModelWithResponseStream`) is **not** granted — the graph never
>   streams. Sonnet/Titan are **not** granted (chat-only; not used by Plane A).
> - **DynamoDB** — only the two actions the store issues: `BatchGetItem`
>   (`dedup_filter`) + `UpdateItem` (`upsert`). No `Scan`/`DeleteItem`/`PutItem`/
>   `Query`. `grant_read_write_data()` is **deliberately not used** (too broad).
>   The GSI ARN is included per the locked decision even though this agent never
>   queries it (writes populate it; Phase 2 reads it).
> - **Secrets Manager** — only `GetSecretValue` on the one Tavily secret ARN
>   (trailing `-*` matches Secrets Manager's 6-char random suffix). No
>   `DescribeSecret`; `grant_read()` is **not** used (adds `DescribeSecret`).
> - **Logs / ECR** — the minimum AgentCore needs to write run logs and pull the
>   image. `ecr:GetAuthorizationToken` is the **sole `Resource: "*"`** — AWS does
>   not support resource-level permissions for it (documented exception).
> - **Deferred (Spec 06):** no `xray:*`, no `cloudwatch:PutMetricData`. The
>   container ships without OTel instrumentation, so no X-Ray calls are made and
>   no such grant is needed here.

## Interfaces

### Public API — `runtime_app.py` (root, CREATE)

New root-level entrypoint, sibling to `run_curation.py`. The AgentCore container
process runs `python runtime_app.py`.

```python
#!/usr/bin/env python3
"""AgentCore Runtime entrypoint for the curation pipeline (Spec 04).

Wraps the UNCHANGED compiled curation graph (Spec 01) in a BedrockAgentCoreApp
handler. Constructs DynamoCardStore (Spec 03) + a composite RSS+Tavily
Discoverer (Specs 01-02) from env only — same wiring as run_curation.py, minus
CLI/rich. The Tavily API key is resolved from Secrets Manager at invocation
time (never baked into the image); on failure the run degrades to RSS-only.

Portability: `bedrock_agentcore` and the Secrets Manager boto3 client are
imported ONLY here (the composition root / infra edge) — never in src/curation/
graph/node/state code, which stays byte-for-byte unchanged from Spec 01.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))   # same as run_curation.py

from bedrock_agentcore import BedrockAgentCoreApp

from curation import config as curation_config
from curation.composite import CompositeDiscoverer
from curation.dynamo import DynamoCardStore
from curation.graph import build_graph
from curation.interfaces import CardStore, Discoverer
from curation.local import RssDiscoverer
from curation.tavily import TavilyDiscoverer
from spike import config

app = BedrockAgentCoreApp()


def _resolve_tavily_key(secret_name: str) -> str:
    """Fetch the Tavily API key from Secrets Manager (client built with region
    from spike.config.AWS_REGION). Return "" on any failure, an empty secret,
    OR a value equal to curation.config.TAVILY_SECRET_UNSET_SENTINEL (the
    CDK-provisioned "not yet populated" placeholder) — the caller then degrades
    to RSS-only (mirrors run_curation.py). boto3 is imported lazily here so
    pytest can patch this function without a real client. NEVER logs the
    secret value."""
    ...


def _build_store() -> CardStore:
    """DynamoCardStore() unconditionally — the Runtime is cloud-only (no JSON
    backend). Table name from curation.config.CARD_TABLE_NAME."""
    return DynamoCardStore()


def _build_discoverer() -> CompositeDiscoverer:
    """RssDiscoverer always; add TavilyDiscoverer.from_config() iff a key
    resolves from Secrets Manager. Resolves the secret, injects it into
    curation.config.TAVILY_API_KEY so from_config() (Spec 02, unchanged) sees
    it, then appends the Tavily source. Degrades to RSS-only otherwise."""
    ...


@app.entrypoint
def handler(payload) -> dict:
    """AgentCore entrypoint. `payload` is accepted (SDK signature) but ignored —
    all config is env-driven. Builds store + discoverer + the UNCHANGED graph,
    invokes it with max_items=spike.config.MAX_ITEMS, and returns a run summary
    (counts). Never raises for a single bad item/source (inherited per-item
    try/except from Specs 01-03)."""
    ...


if __name__ == "__main__":
    app.run()
```

### Config knobs — `src/curation/config.py` (MODIFY: append one block)

Extend the existing module (same env-overridable constant style as Specs 02–03).
Do **not** edit `src/spike/config.py`.

```python
# --- Runtime packaging (Spec 04) -----------------------------------------
# Secrets Manager secret NAME holding the Tavily API key. Resolved at runtime by
# the AgentCore entrypoint (runtime_app.py); the KEY VALUE is never stored here,
# in env at build time, or in the image. Matches the CDK-provisioned secret name.
TAVILY_SECRET_NAME: str = os.getenv("TAVILY_SECRET_NAME", "ai-radar/tavily-api-key")

# Sentinel value the CDK-provisioned Tavily secret (infra/lib/agent_runtime.py)
# is pinned to at deploy time, before a human `put-secret-value`s the real key
# (Task 3.5). NOT env-overridable — a fixed literal that MUST match the
# construct's placeholder value exactly. `runtime_app._resolve_tavily_key`
# treats a secret whose value equals this sentinel as "not yet populated" and
# returns "" (degrade to RSS-only), so a freshly-deployed-but-unpopulated
# secret never gets treated as a real, usable Tavily key.
TAVILY_SECRET_UNSET_SENTINEL: str = "UNSET-populate-via-put-secret-value"
```

> **Why a sentinel, not an empty secret.** AWS Secrets Manager requires
> `SecretString` length ≥ 1, so a literally-empty placeholder is impossible.
> Worse, omitting the value entirely makes CDK synthesize
> `GenerateSecretString: {}`, which AWS fills at deploy time with a **random
> ~32-char password** — truthy, and therefore silently wired into
> `TavilyDiscoverer` as if it were a real key (every search 401s, caught
> per-seed, but `tavily_enabled` would wrongly report `True`). Pinning an
> obviously-non-functional sentinel keeps the secret genuinely inert until
> populated. The constant is **duplicated by design** in
> `infra/lib/agent_runtime.py` (CDK) and `src/curation/config.py` (runtime):
> `infra/` is a separate toolchain/dependency-group and does not import
> `src/curation/`. The two copies are kept in sync by convention, paired
> comments, and a synth test assertion.

> `TAVILY_API_KEY` (Spec 02, unchanged) stays the env fallback for local
> `run_curation.py`; in the Runtime it is left unset and populated at runtime by
> `_build_discoverer` injecting the resolved secret before `from_config()`.

### CDK construct — `infra/lib/agent_runtime.py` (CREATE)

Reusable construct provisioning the **execution role + Tavily placeholder
secret**. Mirrors `infra/lib/card_store.py` (construct exposes attributes for
the stack to output). Imports the already-deployed `ai-radar-cards` table by
name to scope the DynamoDB policy without recreating it.

```python
from __future__ import annotations

from aws_cdk import Aws, RemovalPolicy, SecretValue
from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

# MUST match src/curation/config.py's TAVILY_SECRET_UNSET_SENTINEL exactly.
# Duplicated by design (infra/ is a separate toolchain; it does not import
# src/curation/). See the "Why a sentinel" note above.
TAVILY_SECRET_UNSET_SENTINEL = "UNSET-populate-via-put-secret-value"


class AgentRuntime(Construct):
    """AgentCore Runtime execution role + Tavily API-key secret (Spec 04).

    Exposes `.role` (iam.Role) and `.tavily_secret` (secretsmanager.Secret) for
    the stack to CfnOutput. Least-privilege: see specs/runtime-packaging/
    contract.md for the pinned action/resource list. The card table is REFERENCED
    by name (already deployed by CardStoreStack, RETAINed) — never recreated.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        card_table_name: str = "ai-radar-cards",
        feed_gsi_name: str = "feed-by-score",
        tavily_secret_name: str = "ai-radar/tavily-api-key",
        haiku_inference_profile_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        haiku_foundation_model_id: str = "anthropic.claude-haiku-4-5-20251001-v1:0",
        haiku_regions: list[str] | None = None,   # default ["us-east-1","us-east-2","us-west-2"]
    ) -> None:
        super().__init__(scope, construct_id)
        # 1. Genuinely inert placeholder secret — pinned to the sentinel via
        #    `secret_string_value`, NOT left unset (which would synthesize
        #    `GenerateSecretString` → a random, truthy password at deploy time).
        #    CDK never sets the real value; a human put-secret-value's it
        #    post-deploy. RemovalPolicy.DESTROY so `cdk destroy` cleans it up
        #    (dev secret, trivially re-populated).
        self.tavily_secret = secretsmanager.Secret(
            self, "TavilySecret",
            secret_name=tavily_secret_name,
            secret_string_value=SecretValue.unsafe_plain_text(TAVILY_SECRET_UNSET_SENTINEL),
            removal_policy=RemovalPolicy.DESTROY,
        )
        # 2. Execution role, trust principal bedrock-agentcore.amazonaws.com with
        #    aws:SourceAccount / aws:SourceArn conditions (pinned trust policy).
        self.role = iam.Role(
            self, "ExecutionRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID},
                    "ArnLike": {
                        "aws:SourceArn":
                            f"arn:aws:bedrock-agentcore:{Aws.REGION}:{Aws.ACCOUNT_ID}:*"
                    },
                },
            ),
        )
        # 3. Attach the pinned least-privilege statements (bedrock/dynamo/
        #    secrets/logs/ecr) as explicit iam.PolicyStatement objects — NOT
        #    grant_read_write_data()/grant_read() (both too broad).
        ...
```

### CDK stack + app — `infra/stacks/agent_runtime_stack.py` (CREATE), `infra/app.py` (MODIFY)

```python
# infra/stacks/agent_runtime_stack.py
from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from lib.agent_runtime import AgentRuntime   # infra/ on sys.path via app.py


class AgentRuntimeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        runtime = AgentRuntime(self, "AgentRuntime")
        CfnOutput(self, "ExecutionRoleArn", value=runtime.role.role_arn)
        CfnOutput(self, "TavilySecretArn", value=runtime.tavily_secret.secret_arn)
        CfnOutput(self, "TavilySecretName", value=runtime.tavily_secret.secret_name)
```

```python
# infra/app.py (MODIFY — add the new stack alongside the existing one)
from stacks.agent_runtime_stack import AgentRuntimeStack   # noqa: E402
...
CardStoreStack(app, "AiRadarCardStore")
AgentRuntimeStack(app, "AiRadarRuntimeRole")
app.synth()
```

### Container — root `Dockerfile` + `.dockerignore` (CREATE)

- **Dockerfile**: starter-toolkit-generated, then its dependency step adapted to
  `uv` and committed. Requirements the final image must satisfy:
  - installs deps via **`uv sync --frozen --no-dev`** from `pyproject.toml` +
    `uv.lock` (no `pip`, no `requirements.txt`);
  - copies `src/` and `runtime_app.py`; runs `python runtime_app.py` →
    `app.run()` (AgentCore HTTP contract: port 8080, `/invocations`, `/ping`);
  - **linux/arm64** (AgentCore Runtime requirement — toolkit build handles this);
  - contains **no** Tavily key and **no** `.env`.
- **`.dockerignore`**: excludes `.env`, `.venv/`, `.spike_cache/`, `.git/`,
  `cdk.out/`, `__pycache__/`, `tests/`, `specs/`, `docs/` — critically `.env`
  (holds the local Tavily key) must never enter the build context.

### Dependencies — `pyproject.toml` (MODIFY)

- `bedrock-agentcore` → **main** `dependencies` (imported by `runtime_app.py`;
  must be in the image). `uv add bedrock-agentcore`.
- `bedrock-agentcore-starter-toolkit` → **`dev`** group (local CLI only; not
  imported at runtime, not in the image). `uv add --group dev bedrock-agentcore-starter-toolkit`.
- `aws-cdk-lib`, `constructs` → already in the `infra` group (reused).

## Data Models

No new domain types. `Card`/`RawItem`/`CurationState` are unchanged. The handler
returns a plain run-summary dict (not a new class):

```python
# handler return shape (serialized back to the invoker by AgentCore)
{
    "discovered": int,            # final["discovered"]
    "deduped": int,               # final["deduped"]
    "summarized": int,            # final["summarized"]
    "failed": int,                # final["failed"] (items that raised in summarize)
    "persisted": int,             # len(final["cards"])
    "discoverer_failures": int,   # discoverer.failures()
    "store_failures": int,        # store.failures()
    "tavily_enabled": bool,       # whether the Tavily source was wired this run
}
```

## State Changes

- **No graph state change.** `DynamoCardStore` + the composite discoverer are
  injected into the **unchanged** `build_graph(store, discoverer)`;
  `CurationState`, nodes, edges, `interfaces.py` are untouched.
- **New persistent AWS resources** (via CDK, real deploy): the IAM execution
  role and the Tavily Secrets Manager secret. The `ai-radar-cards` table is
  **referenced, not created** (already deployed, RETAINed).
- **New cloud resources** (via starter toolkit, not CDK): the ECR repository +
  image and the AgentCore Runtime agent/endpoint.
- The container reads the same env knobs as the local run
  (`CARD_TABLE_NAME`, `AWS_REGION`, `SPIKE_MAX_ITEMS`, `SPIKE_PER_FEED`,
  `CURATION_TAVILY_*`, `TAVILY_SECRET_NAME`) — changing them re-targets the same
  image at a dev table with no rebuild.

## Behavior Guarantees

1. **Graph unchanged / portable.** `build_graph`, `nodes.py`, `state.py`,
   `interfaces.py` are byte-for-byte identical to Spec 01. `bedrock_agentcore`
   and the Secrets Manager boto3 client are imported only in `runtime_app.py`;
   `boto3` inside `src/curation/` remains confined to `dynamo.py`.
2. **Env-only config.** The handler ignores `payload`; every knob comes from env
   (via `curation.config` / `spike.config`). The same image run against a
   different `CARD_TABLE_NAME` writes to that table with no rebuild.
3. **Runtime secret resolution.** The Tavily key is read from Secrets Manager at
   invocation time via `secretsmanager:GetSecretValue`. It is never baked into
   the image, the build context, `.env`-in-image, CDK code, or a build-time env
   var. On resolution failure, an empty secret, **or a secret still holding the
   `TAVILY_SECRET_UNSET_SENTINEL` placeholder**, the run proceeds **RSS-only**
   with `tavily_enabled=False` (degrade, don't crash — matches
   `run_curation.py`). The sentinel check guarantees the window between
   `cdk deploy` and the human's `put-secret-value` can never wire a
   non-functional placeholder into `TavilyDiscoverer` as if it were a real key.
4. **Idempotent re-invoke.** Re-invoking is safe: `DynamoCardStore.dedup_filter`
   (Spec 03) skips already-curated items, and `upsert` is insert-or-replace
   preserving `created_at` and the reserved `embedding`.
5. **Per-item/source resilience preserved.** A single bad feed/seed/item/card
   never sinks the run (inherited from Specs 01–03 try/except); the handler
   returns a summary with the failure counters populated.
6. **Least privilege.** The synthesized role policy grants exactly the pinned
   actions/resources above — Haiku-only Bedrock, two DynamoDB actions on the
   table+GSI, one secret's `GetSecretValue`, AgentCore logs + ECR pull. No
   Sonnet/Titan, no `Scan`/`DeleteItem`, no `*` resource except
   `ecr:GetAuthorizationToken`.
7. **Trust scoping.** The role is assumable only by
   `bedrock-agentcore.amazonaws.com` under the `aws:SourceAccount` +
   `aws:SourceArn` conditions.
8. **Handler return.** The handler returns the run-summary dict above; AgentCore
   returns it to the invoker (so `agentcore invoke '{}'` shows the counts, and
   Spec 05's trigger receives them).
9. **Offline tests.** `test_runtime_app.py` mocks `_resolve_tavily_key`,
   `DynamoCardStore`, the discoverers, and `build_graph(...).invoke`; no real AWS
   call. `test_infra_agent_runtime.py` asserts the synthesized template via
   `Template.from_stack`; no `cdk deploy`, no credentials. Real deploy + smoke
   invoke are manual runbook steps.

## Error Handling Contract

| Error Condition | Behavior | User Impact |
|---|---|---|
| Tavily secret missing / `GetSecretValue` denied / throttled | `_resolve_tavily_key` catches the boto3 exception and returns `""`; discoverer is RSS-only; `tavily_enabled=False` in summary | Run completes with RSS items only; no crash |
| Tavily secret resolves but is empty (no `SecretString`) | `_resolve_tavily_key` returns `""` (same path); RSS-only, `tavily_enabled=False` | Run completes with RSS items only; no crash |
| Tavily secret still holds the CDK placeholder (deployed, not yet populated) | value equals `TAVILY_SECRET_UNSET_SENTINEL` → `_resolve_tavily_key` returns `""`; RSS-only, `tavily_enabled=False` | Run completes RSS-only; the summary honestly reports Tavily off, rather than reporting it on while every search 401s |
| One RSS feed / Tavily seed fails | caught + counted inside the discoverer (Specs 01–02); `discoverer_failures` reflects it | Fewer candidates; run completes |
| One item fails to summarize | caught + counted in `summarize_node` (Spec 01); `failed` reflects it | That item skipped; run completes |
| One card fails to persist | caught + counted in `DynamoCardStore.upsert` (Spec 03); `store_failures` reflects it | That card omitted; run completes |
| Table missing / role lacks DynamoDB access | boto3 raises out of the store; the handler run errors loudly | Mis-provisioned infra surfaced (not silently lost); visible in CloudWatch logs |
| Bedrock access denied (role misconfigured) | Converse raises inside `summarize`; caught per-item as a summarize failure, `failed` increments for every item | Empty/low card count + high `failed` signals the mis-scoped role |
| `agentcore launch` build fails (uv/Docker) | surfaced by the toolkit CLI (not runtime) | Operator fixes Dockerfile/deps and re-launches |
| Handler raises unexpectedly | AgentCore returns an error to the invoker; logged to the runtime log group | Operator inspects `agentcore status` / CloudWatch logs |

## Dependencies

- **Internal (imported, not forked):** `curation.graph.build_graph`,
  `curation.dynamo.DynamoCardStore`, `curation.composite.CompositeDiscoverer`,
  `curation.local.RssDiscoverer`, `curation.tavily.TavilyDiscoverer`,
  `curation.interfaces.{CardStore,Discoverer}`, `curation.config` (extended),
  `spike.config` (`AWS_REGION`, `MAX_ITEMS`). No edits to graph/nodes/state/
  interfaces.
- **External (new):** `bedrock-agentcore` (main dep, in image);
  `bedrock-agentcore-starter-toolkit` (dev group, CLI only). `uv` resolves +
  pins versions in `uv.lock`.
- **External (existing):** `boto3` (Secrets Manager client in the entrypoint;
  already a dep), `aws-cdk-lib` + `constructs` (infra group), `langgraph`,
  `feedparser`, `tavily-python`, `python-dotenv` (unchanged).
- **AWS (real, deployed):** the `ai-radar-cards` table + `feed-by-score` GSI
  (already ACTIVE), Bedrock Haiku inference profile (enabled), the new IAM role +
  Tavily secret (this spec deploys), ECR + AgentCore Runtime (toolkit creates).

## Integration Points

- **Spec 01 (curation-graph)** — consumed via the unchanged
  `build_graph(store, discoverer)`; the compiled graph moves onto Runtime with
  zero edits (the portability payoff this spec proves).
- **Spec 02 (tavily-discovery)** — `TavilyDiscoverer.from_config()` reused
  verbatim; the entrypoint injects the Secrets-Manager-resolved key into
  `curation.config.TAVILY_API_KEY` immediately before calling it. This spec adds
  `TAVILY_SECRET_NAME` to `curation.config`.
- **Spec 03 (dynamodb-card-store)** — `DynamoCardStore()` reused verbatim; the
  role scopes DynamoDB to the same table + GSI ARNs. The CDK stack references
  (never recreates) the deployed table; follows the same `infra/` construct →
  stack → app pattern.
- **Spec 05 (eventbridge-daily-schedule)** — imports the `AgentRuntime`
  construct / consumes the deployed agent to attach a schedule; invokes the
  handler with `{}` and receives the run-summary dict. This spec delivers the
  manually-invocable agent it schedules.
- **Spec 06 (run-observability)** — will add `xray:*` / `cloudwatch:PutMetricData`
  grants + OTel instrumentation on top of this role/image; deliberately excluded
  here so the role stays minimal.

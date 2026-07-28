# Intent: runtime-packaging

## Problem Statement

The curation pipeline (Specs 01–03) is fully assembled but only runs from a
laptop via `run_curation.py` against real Bedrock + the deployed
`ai-radar-cards` DynamoDB table. To become a real product, Plane A must run
**unattended in the cloud** on a managed compute surface, not on a developer's
machine. AWS Bedrock **AgentCore Runtime** is the target: a serverless microVM
that hosts a `BedrockAgentCoreApp` handler and bills for wall-clock time — a
good fit because the curation run spends most of its time *waiting* on RSS
fetches and Bedrock calls (design §4, "I/O wait is free").

This spec packages the already-working compiled LangGraph graph as an
AgentCore Runtime agent: a thin `BedrockAgentCoreApp` entrypoint wrapping
`build_graph(...)`, containerized with `uv`, deployed via the
`bedrock-agentcore-starter-toolkit`, running under a **custom least-privilege
IAM execution role** authored in CDK, with the **Tavily API key resolved from
Secrets Manager at runtime** (never baked into the image). Real AWS
infrastructure already exists: Spec 03 (`dynamodb-card-store`) delivered the
`CardStoreStack`, which is deployed with the `ai-radar-cards` table + its
`feed-by-score` GSI ACTIVE in `us-east-1`. What is new here is (a) the first
**security-sensitive** resources — an IAM execution role and a Secrets Manager
secret, rather than a passive data store; (b) the first **cloud-hosted,
invocable agent** (container image + Runtime endpoint), so the pipeline finally
*runs* in AWS instead of only storing there; and (c) the first spec whose own
deliverable includes performing the `cdk deploy` and a live smoke test — Specs
01–03 scoped themselves to a `cdk synth`-able app and left the actual deploy to
the human. Spec 05 later adds the EventBridge schedule; this spec makes the
agent manually invocable.

Who is affected: the operator (deploys + invokes the agent) and every
downstream spec (05 scheduling, 06 observability) that assumes a deployed
Runtime agent exists.

## Goals

1. Wrap the **unchanged** compiled curation graph in a `BedrockAgentCoreApp`
   entrypoint (`runtime_app.py`) that constructs `DynamoCardStore()` +
   `CompositeDiscoverer([RssDiscoverer(), TavilyDiscoverer.from_config()])`
   from environment only (same construction pattern as `run_curation.py`, minus
   the CLI/rich-console parts) and invokes the graph, returning a run summary.
2. Resolve the **Tavily API key from AWS Secrets Manager at invocation time**,
   never from the built image or a build-time env var; degrade to RSS-only if
   the secret is absent/unreadable (mirroring `run_curation.py`'s auto-select).
3. Containerize with **`uv`** (deps from `pyproject.toml` + `uv.lock`, `src/`
   included), producing an AgentCore-contract-compliant image via the starter
   toolkit — no `pip`/`requirements.txt`, no secret baked in.
4. Author a **custom least-privilege IAM execution role in CDK** (new construct
   + stack under `infra/`, following the `CardStoreTable`/`CardStoreStack`
   pattern) and pass its ARN to the toolkit via
   `agentcore configure --execution-role <arn>` — the toolkit must **not**
   auto-generate its own role.
5. Provision the Tavily **Secrets Manager secret in CDK** pinned to a fixed,
   obviously-non-functional **sentinel** value
   (`TAVILY_SECRET_UNSET_SENTINEL = "UNSET-populate-via-put-secret-value"`) —
   CDK never contains the real key. The placeholder cannot be literally empty:
   AWS Secrets Manager requires `SecretString` length ≥ 1, and leaving the
   value unset makes CDK emit `GenerateSecretString`, which AWS fills with a
   random ~32-char password that is *truthy but useless*. The entrypoint
   therefore treats the sentinel as "not yet populated" and degrades to
   RSS-only. The role's policy references only that one secret ARN.
6. **`cdk deploy`** the new role + secret stack for real *as part of this spec's
   own deliverable* — Specs 01–03 scoped themselves to synth/moto verification
   and deferred the actual deploy to the human (Spec 03's `CardStoreStack` was
   deployed that way and is live) — then deploy + smoke-invoke the agent and
   confirm cards land in DynamoDB.
7. Deliver a **runbook**: prerequisites, deploy, populate-secret, smoke-test,
   and teardown (delete Runtime + ECR image + role/secret stack) commands.

## Success Criteria

- [ ] `agentcore launch` (documented equivalent of `agentcore deploy`) builds
      the container from the uv-locked deps and creates a working Runtime agent.
- [ ] Invoking the deployed agent (`agentcore invoke '{}'`) runs the full graph
      and writes/updates cards in the `ai-radar-cards` DynamoDB table.
- [ ] The execution role is least-privilege: `bedrock:InvokeModel` scoped to the
      Haiku inference-profile + its per-region foundation-model ARNs only,
      DynamoDB scoped to the `ai-radar-cards` table + `feed-by-score` GSI ARNs
      only, `secretsmanager:GetSecretValue` scoped to the single Tavily secret
      ARN only, and CloudWatch Logs / ECR-pull scoped to AgentCore paths. The
      only unavoidable `Resource: "*"` is `ecr:GetAuthorizationToken` (AWS does
      not support resource-level scoping for it) — documented for review.
- [ ] No Sonnet/Titan model access, no `dynamodb:DeleteItem`/`Scan`, no `*`
      table/secret resources in the role.
- [ ] The Tavily key is resolved from Secrets Manager at runtime; `grep`-ing the
      image / build context / CDK code never reveals it.
- [ ] The entrypoint reads all config from env; the same image runs against a
      dev table by changing `CARD_TABLE_NAME` (and friends) only — no rebuild.
- [ ] A teardown step (delete Runtime + ECR image via `agentcore destroy`, then
      `cdk destroy` the role/secret stack) is documented and leaves the RETAINED
      `ai-radar-cards` table intact.
- [ ] Graph/node/state/interface code from Spec 01 is byte-for-byte unchanged
      (packaging only — proves portability).
- [ ] `pytest` remains 100% offline: entrypoint handler unit-tested with
      store/discoverer/graph/secret mocked; the new CDK stack synth-tested via
      `Template.from_stack`. The real deploy + smoke invoke is a manual runbook
      step, not an automated test (mirrors Spec 02's live-Tavily precedent).

## Non-Goals

- **EventBridge scheduling** — Spec 05. This spec makes the agent manually
  invocable only.
- **Observability beyond default CloudWatch logs** — Spec 06. No X-Ray tracing,
  no custom CloudWatch metrics, no OTel instrumentation in this spec (and so no
  `xray:*` / `cloudwatch:PutMetricData` grants in the role).
- **The chat agent / Plane B / AgentCore Memory** — Phase 3. The role grants no
  Sonnet or Titan model access.
- **Changing the curation graph, nodes, state, interfaces, discoverers, or the
  Dynamo store** — this is packaging. Any change there is out of scope and would
  violate the portability guarantee.
- **Re-deploying or altering the `ai-radar-cards` table** — it is already
  deployed (ACTIVE) by `CardStoreStack` and is RETAINed; this spec only
  references its ARN.
- **A production multi-account / multi-region posture** — single account
  (`536697225154`), single source region (`us-east-1`).

## Constraints

- **uv only** — deps live in `pyproject.toml` + `uv.lock`; the container installs
  via `uv sync --frozen`. No `pip`, `venv`, or `requirements.txt`.
- **Portability** — `bedrock-agentcore` is imported only in the root entrypoint
  (`runtime_app.py`, the composition root / infra edge), never in
  `src/curation/` graph/node/state/interface code. `boto3` for Secrets Manager
  lives only in the root entrypoint; `src/curation/dynamo.py` remains the only
  boto3 importer inside `src/curation/`.
- **Cost discipline ($500 credits)** — the role grants Haiku only (bulk
  summarize); no Sonnet/Titan. AgentCore Runtime bills wall-clock; the run's
  cost lever remains `SPIKE_MAX_ITEMS` / `CURATION_TAVILY_MAX_RESULTS`.
- **Cross-region inference profiles** — the graph invokes Haiku via the `us.`
  inference profile; the IAM policy must therefore grant the inference-profile
  ARN **and** the underlying foundation-model ARNs in every region the profile
  spans (verified requirement, not a bare model ARN).
- **Secret never in code/image** — CDK creates a sentinel-valued placeholder
  secret only; the real value is `put-secret-value`'d by a human post-deploy.
  The sentinel must be inert (never mistaken for a usable key) and identical on
  both sides — `infra/lib/agent_runtime.py` and `src/curation/config.py`.
  `.dockerignore` must exclude `.env`.
- **Least privilege / no `*` resources** — every ARN scoped except the single
  AWS-mandated `ecr:GetAuthorizationToken` exception, which is documented.
- **Real deploy required** — the new CDK stack must actually be `cdk deploy`'d
  and the agent actually launched + smoke-invoked (human runbook step), not just
  synth-tested.
- **AgentCore contract** — the container must expose the SDK's HTTP contract
  (port 8080, `/invocations`, `/ping`); the starter toolkit generates a
  compliant Dockerfile which is then adapted to `uv` and committed.

## Prior Art

- **`run_curation.py`** — the existing manual entrypoint; `runtime_app.py`
  reuses its exact construction pattern (`DynamoCardStore()`, composite
  RSS+Tavily discoverer, `build_graph(store, discoverer).invoke(...)`) minus the
  CLI/rich parts.
- **`src/curation/dynamo.py`** — the boto3 infra-edge adapter precedent
  (lazy-singleton client, region from `spike.config.AWS_REGION`); the entrypoint's
  Secrets Manager client mirrors this lazy-singleton style.
- **`spike/bedrock.py`** — lazy-singleton `bedrock_client()` pattern.
- **`infra/lib/card_store.py` + `infra/stacks/card_store_stack.py` + `infra/app.py`**
  — the CDK construct → stack → app composition pattern this spec follows for the
  new role + secret stack; `tests/test_infra.py` is the synth-test precedent.
- **Spec 02 Task 3.2** — the "live third-party smoke test left as a manual step
  for the human" precedent, extended here to the real deploy + smoke invoke.
- **External:** `bedrock-agentcore` SDK (`BedrockAgentCoreApp`/`@app.entrypoint`)
  and `bedrock-agentcore-starter-toolkit` (`agentcore configure/launch/status/
  invoke/destroy`); AgentCore Runtime execution-role permissions + trust policy
  reference (verified via Context7, 2026-07).

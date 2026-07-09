# Spec 04 — AgentCore Runtime packaging

- **feature-name:** `runtime-packaging`
- **SDD target dir:** `specs/runtime-packaging/`
- **Depends on:** Spec 01 (graph), Spec 02 (Tavily secret), Spec 03 (Dynamo store)
- **Layer:** Infra (AgentCore Runtime)

## Intent

Package the curation graph as an **AgentCore Runtime agent** so it runs in a
managed microVM instead of on a laptop. Wrap the compiled LangGraph graph in a
`BedrockAgentCoreApp` entrypoint, containerize it, wire a least-privilege IAM
execution role, and deploy via the starter toolkit. After this spec, the pipeline
is invocable in the cloud (manually); Spec 05 adds the schedule.

The design's whole rationale for Runtime here is the **"I/O wait is free"**
billing — the pipeline spends most of its time waiting on RSS fetches and Bedrock
calls (§4).

## Background

Research doc §2.1: Runtime exposes a `BedrockAgentCoreApp` Python class as the
entry point; the starter toolkit (`agentcore deploy/status`) builds & pushes the
container to ECR, creates the Runtime instance, and auto-wires IAM. SDK packages:
`bedrock-agentcore`, `bedrock-agentcore-starter-toolkit` (add via `uv add`).

## Scope

**In scope**
- A Runtime entrypoint module that constructs the graph with the **DynamoCardStore**
  (Spec 03) + the composite **RSS + Tavily `Discoverer`** (Specs 01–02) and runs it
  when invoked:
  ```python
  from bedrock_agentcore.runtime import BedrockAgentCoreApp
  app = BedrockAgentCoreApp()

  @app.entrypoint
  def handler(payload):
      # build graph with DynamoCardStore + composite RSS+Tavily discoverer,
      # invoke, return run summary
      ...
  ```
- Config via environment (region, model IDs, table name, `MAX_ITEMS`, `PER_FEED`,
  Tavily secret name + seeds) — reuse the `config.py` env-override pattern.
- **Secret resolution**: read the Tavily API key (Spec 02) from **Secrets Manager**
  at startup/invocation; never bake it into the image or env at build time.
- Containerization: Dockerfile (or starter-toolkit-generated) that installs deps
  **via uv** from `pyproject.toml`/`uv.lock` and includes `src/`.
- A **least-privilege IAM execution role** for the Runtime: `bedrock:InvokeModel`
  on the specific Haiku/Titan model ARNs, DynamoDB read/write on the Spec 03 table +
  GSI, `secretsmanager:GetSecretValue` on **only** the Tavily key secret ARN, and
  CloudWatch Logs. No `*` resource grants.
- A `deploy` runbook (commands + prerequisites) and a smoke-test: invoke the
  deployed agent once and confirm cards land in DynamoDB.
- Idempotent invocation: a manual re-invoke is safe (relies on Spec 03 dedup).

**Out of scope**
- EventBridge scheduling (Spec 05).
- Observability beyond default logs (Spec 06 deepens it).
- The chat agent / Memory (Phase 3).

## Acceptance criteria

- [ ] `agentcore deploy` (or documented equivalent) builds the container from the
      uv-locked deps and creates a working Runtime agent.
- [ ] Invoking the deployed agent runs the full graph and writes cards to DynamoDB.
- [ ] The execution role is least-privilege (named model ARNs + the one table/GSI +
      the single Tavily secret ARN + logs); no wildcard resources. Documented and
      reviewable.
- [ ] The Tavily key is resolved from Secrets Manager at runtime, never from the
      built image.
- [ ] Entrypoint reads all config from env; the same image runs against a dev table
      by changing env only.
- [ ] A teardown step (delete Runtime + ECR image) is documented.
- [ ] Graph node code is unchanged from Spec 01 (packaging only — proves portability).

## SDD note

Feed to `sdd-architect` as `runtime-packaging`. Use the **Context7 MCP** to pull
current `bedrock-agentcore` / starter-toolkit entrypoint + deploy APIs before
authoring (per global rules) — do not rely on the research doc snippets alone, they
may be stale. The contract should pin the IAM action/resource list.

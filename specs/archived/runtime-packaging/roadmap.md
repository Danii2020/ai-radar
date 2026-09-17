# Roadmap: runtime-packaging

## Implementation Phases

### Phase 1: Dependencies & entrypoint (Foundation)
**Goal**: Add the SDK/toolkit deps and the `BedrockAgentCoreApp` entrypoint that
wraps the unchanged graph, resolving the Tavily key from Secrets Manager.
**Dependencies**: None (Specs 01–03 already landed).
**Estimated complexity**: Medium

1. `uv add bedrock-agentcore` (main dep — imported by the entrypoint, must be in
   the image). `uv add --group dev bedrock-agentcore-starter-toolkit` (CLI only).
   Confirm `uv.lock` updates and `uv sync` succeeds.
2. Append the `TAVILY_SECRET_NAME` knob to `src/curation/config.py` (do **not**
   touch `src/spike/config.py`).
3. Create `runtime_app.py` at repo root: `sys.path.insert(0, "src")`, construct
   `BedrockAgentCoreApp`, implement `_resolve_tavily_key` (lazy-singleton
   `boto3.client("secretsmanager", region_name=spike.config.AWS_REGION)`,
   returns `""` on any failure, never logs the value), `_build_store`
   (`DynamoCardStore()`), `_build_discoverer` (RSS always; inject resolved key
   into `curation.config.TAVILY_API_KEY` then append `TavilyDiscoverer.from_config()`),
   and the `@app.entrypoint def handler(payload)` returning the run-summary dict.
   Guard `app.run()` with `if __name__ == "__main__":`.
4. Confirm `src/curation/{graph,nodes,state,interfaces}.py` remain unmodified
   (`git diff` clean for those paths).

### Phase 2: CDK role + secret stack (Foundation, parallel to Phase 1)
**Goal**: Author the least-privilege execution role + Tavily placeholder secret
as a reusable construct + stack, synth-clean.
**Dependencies**: None (independent of Phase 1; both feed Phase 3).
**Estimated complexity**: Medium

1. Create `infra/lib/agent_runtime.py` → `AgentRuntime` construct: placeholder
   `secretsmanager.Secret` (name `ai-radar/tavily-api-key`,
   `removal_policy=DESTROY`, no real value); `iam.Role` with the pinned trust
   policy (principal `bedrock-agentcore.amazonaws.com` + `aws:SourceAccount`/
   `aws:SourceArn` conditions); attach the pinned least-privilege
   `iam.PolicyStatement`s (bedrock Haiku, dynamo BatchGetItem+UpdateItem on
   table+GSI, secrets GetSecretValue on the secret, logs, ECR). Use explicit
   statements — **not** `grant_read_write_data()`/`grant_read()`. Reference the
   table ARN by name (`Aws.ACCOUNT_ID`/`Aws.REGION` tokens), don't recreate it.
2. Create `infra/stacks/agent_runtime_stack.py` → `AgentRuntimeStack` wrapping
   the construct, with `CfnOutput`s for `ExecutionRoleArn`, `TavilySecretArn`,
   `TavilySecretName`.
3. Modify `infra/app.py` to add `AgentRuntimeStack(app, "AiRadarRuntimeRole")`
   alongside the existing `CardStoreStack` (keep the `sys.path`/flat-module
   pattern).
4. `uv run python infra/app.py` (or `uv run cdk synth AiRadarRuntimeRole`)
   synthesizes cleanly.

### Phase 3: Containerize & deploy (Integration)
**Goal**: Build the uv-based image, deploy the role/secret stack for real, and
create the Runtime agent under the custom role.
**Dependencies**: Phase 1 + Phase 2.
**Estimated complexity**: High

1. Create root `.dockerignore` excluding `.env`, `.venv/`, `.spike_cache/`,
   `.git/`, `cdk.out/`, `__pycache__/`, `tests/`, `specs/`, `docs/`.
2. `agentcore configure -e runtime_app.py --execution-role <arn>` to generate
   the Dockerfile + `.bedrock_agentcore.yaml`. Adapt the generated Dockerfile's
   dependency step to `uv sync --frozen --no-dev` (from `pyproject.toml`/
   `uv.lock`), ensure `src/` + `runtime_app.py` are copied and the AgentCore
   HTTP contract (port 8080/`/invocations`/`/ping`, arm64) is preserved. Commit
   the final Dockerfile + `.bedrock_agentcore.yaml` (no secrets in either).
3. **Real deploy step 1**: `uv run cdk deploy AiRadarRuntimeRole` — capture the
   `ExecutionRoleArn` + `TavilySecretArn` outputs. (The `AiRadarCardStore` table
   is already deployed; do **not** redeploy it.)
4. Verify the Haiku `us.` inference profile's member regions
   (`aws bedrock get-inference-profile --inference-profile-identifier
   us.anthropic.claude-haiku-4-5-20251001-v1:0`); if they differ from
   us-east-1/us-east-2/us-west-2, adjust `haiku_regions` and re-`cdk deploy`.
5. **Populate the secret** (human, never CDK/image): `aws secretsmanager
   put-secret-value --secret-id ai-radar/tavily-api-key --secret-string <key>`.
6. Wire the execution-role ARN into `agentcore configure` (if not passed in
   step 2), set the container env (`CARD_TABLE_NAME`, `TAVILY_SECRET_NAME`,
   tuning knobs), then `agentcore launch` to build (arm64) + push to ECR +
   create the Runtime agent.

### Phase 4: Testing, smoke & runbook (Testing & Validation)
**Goal**: Prove correctness offline, smoke-test the live agent, and document the
full deploy/teardown runbook.
**Dependencies**: Phase 3.
**Estimated complexity**: Medium

1. Write `tests/test_runtime_app.py` (offline): patch `_resolve_tavily_key`,
   `DynamoCardStore`, the discoverers, and `build_graph(...).invoke`; assert the
   handler returns the correct run-summary dict, ignores `payload`, and degrades
   to RSS-only (`tavily_enabled=False`) when the key resolves empty.
2. Write `tests/test_infra_agent_runtime.py` (synth-only, mirrors
   `tests/test_infra.py`): `Template.from_stack(AgentRuntimeStack(...))`; assert
   the trust policy principal + conditions, the four scoped statements
   (bedrock/dynamo/secrets/logs+ecr), absence of Sonnet/Titan/`Scan`/`DeleteItem`,
   and that the only `Resource:"*"` is `ecr:GetAuthorizationToken`; assert the
   secret exists with no plaintext value.
3. `uv run pytest` green + 100% offline (no AWS calls).
4. **Manual smoke** (human, real creds): `agentcore invoke '{}'` returns a
   run-summary with `persisted > 0`; confirm cards via
   `aws dynamodb scan --table-name ai-radar-cards --select COUNT` (or a
   `feed-by-score` query). Re-invoke to confirm idempotent dedup.
5. Write the runbook + update `README.md` + `.env.example` (document
   `TAVILY_SECRET_NAME` and that the Runtime resolves the key from Secrets
   Manager). Document teardown: `agentcore destroy` (Runtime + ECR), then
   `uv run cdk destroy AiRadarRuntimeRole` (role + secret) — leaving the RETAINed
   `ai-radar-cards` table intact.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Starter-toolkit generated Dockerfile assumes pip/requirements.txt, not uv | High | Med | Adapt the dep step to `uv sync --frozen`; commit the final Dockerfile; verify `uv.lock` is in the build context |
| `us.` Haiku profile spans different/more regions than assumed → `AccessDenied` on Bedrock | Med | High | Verify member regions via `get-inference-profile` at deploy (Phase 3.4); parameterize `haiku_regions` in the construct |
| `src/` layout + `package=false` not on `sys.path` inside the container | Med | High | `runtime_app.py` does `sys.path.insert(0, "src")` itself (same as `run_curation.py`); Dockerfile copies `src/` to the workdir |
| Secret accidentally baked into image (via `.env` in build context) | Low | High | `.dockerignore` excludes `.env`; test asserts CDK has no plaintext; runbook uses `put-secret-value` only |
| `agentcore configure` auto-creates its own role, bypassing least-privilege | Med | High | Always pass `--execution-role <arn>`; verify `.bedrock_agentcore.yaml` references the CDK role ARN |
| Role too tight → runtime can't pull image / write logs | Med | Med | Include the pinned ECR-pull + logs statements; smoke-test surfaces gaps in CloudWatch |
| arm64 build fails locally (no buildx / wrong arch) | Low | Med | Let the toolkit drive the arm64 build (CodeBuild or buildx); documented as a prereq |
| Secret `RemovalPolicy.DESTROY` deletes a populated key on teardown | Low | Low | Documented in the runbook; the key is trivially re-`put`; acceptable for a dev secret |
| Runtime cost surprise (wall-clock billing) | Low | Med | `SPIKE_MAX_ITEMS`/`CURATION_TAVILY_MAX_RESULTS` cap work; Haiku-only; teardown documented |

## File Change Map

- `pyproject.toml` — MODIFY — add `bedrock-agentcore` (main) +
  `bedrock-agentcore-starter-toolkit` (dev group); `uv.lock` regenerated.
- `uv.lock` — MODIFY (generated) — pinned resolutions for the new deps.
- `src/curation/config.py` — MODIFY — append the `TAVILY_SECRET_NAME` knob.
- `runtime_app.py` — CREATE — `BedrockAgentCoreApp` entrypoint (handler + secret
  resolution + store/discoverer wiring; guarded `app.run()`).
- `infra/lib/agent_runtime.py` — CREATE — `AgentRuntime` construct (execution
  role + Tavily placeholder secret; least-privilege policy).
- `infra/stacks/agent_runtime_stack.py` — CREATE — `AgentRuntimeStack` + outputs.
- `infra/app.py` — MODIFY — add `AgentRuntimeStack(app, "AiRadarRuntimeRole")`.
- `Dockerfile` — CREATE — uv-based, arm64, AgentCore-contract image (toolkit-
  generated then adapted + committed).
- `.dockerignore` — CREATE — exclude `.env`, `.venv/`, caches, tests, specs, docs.
- `.bedrock_agentcore.yaml` — CREATE (generated by `agentcore configure`,
  committed) — agent name/region/entrypoint/role ARN/ECR; no secrets.
- `tests/test_runtime_app.py` — CREATE — offline handler unit test (mocks).
- `tests/test_infra_agent_runtime.py` — CREATE — synth-only stack test.
- `.env.example` — MODIFY — document `TAVILY_SECRET_NAME` + runtime secret
  resolution.
- `README.md` — MODIFY — document the Runtime entrypoint + deploy/teardown
  runbook (mirrors prior specs updating README).
- `src/curation/{graph,nodes,state,interfaces}.py` — UNCHANGED (asserted) —
  portability guarantee.

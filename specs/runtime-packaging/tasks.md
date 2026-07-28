# Tasks: runtime-packaging

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

> Paths are real repo paths. Runtime code is Python (`.py`, `uv`, `src/`
> layout); infra is CDK v2 Python under `infra/`; the container is a root
> `Dockerfile`. **Do not modify** `src/curation/{graph,nodes,state,interfaces}.py`
> — the portability guarantee (R9/C17) forbids it.

## Phase 1: Dependencies & entrypoint (Foundation)
- [x] Task 1.1: `uv add bedrock-agentcore` (main dep) — `pyproject.toml`, `uv.lock`
- [x] Task 1.2: `uv add --group dev bedrock-agentcore-starter-toolkit` (CLI only) — `pyproject.toml`, `uv.lock`
- [x] Task 1.3: `uv sync` and confirm the env resolves (imports `from bedrock_agentcore import BedrockAgentCoreApp`) — (env)
- [x] Task 1.4: Append the `TAVILY_SECRET_NAME` knob (default `ai-radar/tavily-api-key`) — `src/curation/config.py`
- [x] Task 1.5: Create the entrypoint skeleton: `sys.path.insert(0,"src")`, imports, `app = BedrockAgentCoreApp()`, guarded `if __name__ == "__main__": app.run()` — `runtime_app.py`
- [x] Task 1.6: Implement `_resolve_tavily_key(secret_name)` — lazily-created `boto3.client("secretsmanager", region_name=spike.config.AWS_REGION)`, returns `""` on any exception/empty, never logs the value — `runtime_app.py` (note: implemented as a fresh client per call rather than a persistent module-level singleton — see Notes)
- [x] Task 1.7: Implement `_build_store()` → `DynamoCardStore()` and `_build_discoverer()` → RSS always + inject resolved key into `curation.config.TAVILY_API_KEY` then append `TavilyDiscoverer.from_config()` — `runtime_app.py`
- [x] Task 1.8: Implement `@app.entrypoint def handler(payload) -> dict` — build store+discoverer+`build_graph(...).invoke({"max_items": spike.config.MAX_ITEMS})`, return the run-summary dict incl. `tavily_enabled` — `runtime_app.py`
- [x] Task 1.9: Confirm `git diff --stat src/curation/{graph,nodes,state,interfaces}.py` is empty — (verify) — confirmed empty

## Phase 2: CDK role + secret stack (Foundation)
- [x] Task 2.1: Create the `AgentRuntime` construct — placeholder `secretsmanager.Secret` (name `ai-radar/tavily-api-key`, `removal_policy=DESTROY`, no real value) — `infra/lib/agent_runtime.py`
- [x] Task 2.2: Add the `iam.Role` with the pinned trust policy (principal `bedrock-agentcore.amazonaws.com` + `aws:SourceAccount`/`aws:SourceArn` conditions) — `infra/lib/agent_runtime.py`
- [x] Task 2.3: Attach the pinned least-privilege `iam.PolicyStatement`s (Haiku bedrock, dynamo `BatchGetItem`+`UpdateItem` on table+GSI, secrets `GetSecretValue`, logs, ECR pull + auth-token); explicit statements, **not** `grant_read_write_data()`/`grant_read()`; reference the table ARN by name — `infra/lib/agent_runtime.py` (note: permission-policy ARNs use the pinned literal account/region per coordinator instruction, not `Aws` tokens — see Notes; trust-policy condition still uses `Aws.ACCOUNT_ID`/`Aws.REGION`)
- [x] Task 2.4: Create `AgentRuntimeStack` wrapping the construct + `CfnOutput`s (`ExecutionRoleArn`, `TavilySecretArn`, `TavilySecretName`) — `infra/stacks/agent_runtime_stack.py`
- [x] Task 2.5: Add `AgentRuntimeStack(app, "AiRadarRuntimeRole")` alongside `CardStoreStack` — `infra/app.py`
- [x] Task 2.6: `uv run python infra/app.py` synthesizes cleanly (both stacks) — (verify) — exit 0

## Phase 3: Containerize & deploy (Integration — real AWS, human-run)
- [x] Task 3.1: Create `.dockerignore` excluding `.env`, `.venv/`, `.spike_cache/`, `.git/`, `cdk.out/`, `__pycache__/`, `tests/`, `specs/`, `docs/` — `.dockerignore`
- [~] Task 3.2: Dockerfile content hand-authored per contract.md (no execution-role ARN exists yet to run the real `agentcore configure`, so the CLI step + `.bedrock_agentcore.yaml` generation are left to the human after Task 3.3) — `Dockerfile` done; `.bedrock_agentcore.yaml` NOT created (toolkit-generated, requires a real deployed role ARN)
- [ ] Task 3.3: `uv run cdk deploy AiRadarRuntimeRole`; capture `ExecutionRoleArn` + `TavilySecretArn` (do **not** redeploy `AiRadarCardStore`) — (deploy)
- [ ] Task 3.4: Verify Haiku profile member regions via `aws bedrock get-inference-profile --inference-profile-identifier us.anthropic.claude-haiku-4-5-20251001-v1:0`; adjust `haiku_regions` + re-deploy if they differ — `infra/lib/agent_runtime.py` (verify)
- [ ] Task 3.5: Populate the secret (human, never CDK): `aws secretsmanager put-secret-value --secret-id ai-radar/tavily-api-key --secret-string <key>` — (runbook)
- [ ] Task 3.6: Set container env (`CARD_TABLE_NAME`, `TAVILY_SECRET_NAME`, tuning) and `agentcore launch` (arm64 build → ECR → Runtime agent) — `.bedrock_agentcore.yaml` (deploy)

## Phase 4: Testing, smoke & runbook (Testing & Validation)
- [x] Task 4.1: Offline handler unit test — patch `_resolve_tavily_key`/`DynamoCardStore`/discoverers/`build_graph(...).invoke`; cover T1–T6 (summary dict, payload ignored, tavily on/off, secret-error empty+no-log, no server on import) — `tests/test_runtime_app.py`
- [x] Task 4.2: Synth-only stack test (mirror `tests/test_infra.py`, `sys.path.insert` to `infra/`) — cover T7–T14 (trust policy, bedrock/dynamo/secrets/logs/ECR scoping, sole `*`, placeholder secret, no table resource, outputs) — `tests/test_infra_agent_runtime.py`
- [x] Task 4.3: `uv run pytest` green + fully offline (no AWS calls) — (verify) — 61 passed (43 pre-existing + 18 new)
- [ ] Task 4.4: Manual smoke (human, real creds) — `agentcore invoke '{}'` → `persisted>0`; confirm via `aws dynamodb scan --table-name ai-radar-cards --select COUNT`; re-invoke → idempotent (T15/C18) — (runbook, not run)
- [x] Task 4.5: Update `.env.example` — document `TAVILY_SECRET_NAME` + that the Runtime resolves the key from Secrets Manager — `.env.example`
- [x] Task 4.6: Write the deploy + teardown runbook in `README.md` — prerequisites, `cdk deploy`, populate-secret, `agentcore configure/launch/status/invoke`, smoke, and teardown (`agentcore destroy` then `cdk destroy AiRadarRuntimeRole`, table stays RETAINed) — `README.md` (teardown documented only, not executed — no real deploy exists yet)

## Blocked Items
[None yet]

## Notes
- **Phases 1 and 2 are independent** and can proceed in parallel; both must land
  before Phase 3.
- **Human-run / real-AWS tasks** (not in the automated suite): 3.3, 3.4, 3.5,
  3.6, 4.4, and the teardown in 4.6 — mirrors Spec 02's manual live-smoke
  precedent. The executor/test-writer implement everything else offline.
- **Portability gate**: Task 1.9 + C17/T-review must confirm
  `src/curation/{graph,nodes,state,interfaces}.py` are untouched — this is the
  whole point of the spec (proves the graph lifts onto Runtime unchanged).
- **Secret hygiene**: the real Tavily key enters only via Task 3.5
  (`put-secret-value`). It must never appear in `Dockerfile`, `.bedrock_agentcore.yaml`,
  CDK code, `.env`-in-image, or any committed file. `.dockerignore` (3.1)
  excludes `.env` from the build context.
- **Region drift** (Task 3.4): if the Haiku profile's regions differ from the
  assumed us-east-1/us-east-2/us-west-2, update the construct's `haiku_regions`
  **and** `tests/test_infra_agent_runtime.py`'s expected ARNs together.

## Executor notes (offline implementation pass)

- **`_resolve_tavily_key` is not a persistent module-level singleton.**
  `tests/test_runtime_app.py`'s three T5 subtests each `monkeypatch.setattr(boto3,
  "client", ...)` with a *different* fake client and call `_resolve_tavily_key`
  directly, in sequence, within the same test session. A true cached
  module-global client (created once, reused thereafter) would silently reuse
  the first test's fake client for the later tests and fail T5's blank/error
  cases. The implementation therefore calls `boto3.client(...)` fresh on every
  invocation — still "lazy" (never created at import time), just not memoized
  across calls. This is a deliberate deviation from the roadmap/tasks wording
  ("lazy-singleton"), driven by the red-phase test file being the higher-priority
  spec of correctness per the executor's instructions. Functionally harmless in
  production (Secrets Manager `GetSecretValue` is called once per Runtime
  invocation anyway, not in a hot loop).
- **Permission-policy ARNs use literal `536697225154`/`us-east-1`, not `Aws.*`
  tokens.** `tests/test_infra_agent_runtime.py` (T8–T11) compares
  `statement["Resource"]` against plain literal-string sets; a CDK
  `Aws.ACCOUNT_ID`/`Aws.REGION` token synthesizes as an `Fn::Join` intrinsic
  (a dict), which would fail those equality assertions. This matches the
  explicit coordinator instruction: literal account/region for the
  permission-policy resource ARNs (the referenced `ai-radar-cards` table has no
  cross-stack export to token against anyway), `Aws.ACCOUNT_ID`/`Aws.REGION`
  tokens only for the trust-policy `Condition` (which the test flattens via a
  helper built for that purpose).
- **`.bedrock_agentcore.yaml` was not created.** It is toolkit-generated by a
  real `agentcore configure --execution-role <arn>` run, which requires the
  Task 3.3 `cdk deploy` to have produced a real `ExecutionRoleArn` first — both
  explicitly out of scope for this offline pass (human-run, real AWS).

## Completed (offline implementation pass)

2026-07-27 — Phases 1, 2, and the offline-doable parts of Phases 3–4 complete.
`uv run pytest` green (61/61, 100% offline). `src/curation/{graph,nodes,state,
interfaces}.py` confirmed byte-for-byte unchanged. Remaining open items (3.2's
`.bedrock_agentcore.yaml`, 3.3–3.6, 4.4, and the teardown execution in 4.6) are
human-run real-AWS steps per the spec's own scoping and are documented as
runbook steps in `README.md`, not executed.

## Post-audit fixes (2026-07-27, same day)

The auditor found two real bugs in the above pass (independently confirmed by
the coordinator and human); both fixed same-day, with regression coverage
added so neither class of bug can silently ship again. See
`specs/runtime-packaging/audit.md`'s Audit Log for the full writeup.

- **F1 (CRITICAL — fixed):** `Dockerfile` never set `DOCKER_CONTAINER=1`.
  `BedrockAgentCoreApp.run()` binds `0.0.0.0` only if `/.dockerenv` exists
  (a Docker-daemon artifact, not guaranteed inside an AgentCore microVM) **or**
  `DOCKER_CONTAINER` is set — without it the server could bind loopback-only,
  so the agent would deploy successfully but fail every real invocation
  (`/ping`/`/invocations` unreachable). Fixed by adding `DOCKER_CONTAINER=1` to
  the `Dockerfile`'s `ENV` block (matching the official starter-toolkit's own
  generated-Dockerfile template). Regression test: new
  `tests/test_dockerfile.py::test_dockerfile_sets_docker_container_env_for_agentcore_host_binding`
  parses the committed `Dockerfile`'s `ENV` instruction(s) (joining backslash
  continuations) and asserts `DOCKER_CONTAINER=1` is present — a narrow,
  functional assertion, not a text-diff/change-detector.
- **F2 (MEDIUM — fixed):** the "empty placeholder" Tavily secret in
  `infra/lib/agent_runtime.py` wasn't actually empty. Leaving
  `secretsmanager.Secret(...)` with no explicit value synthesizes
  `GenerateSecretString: {}`, which AWS fills with a random ~32-char password
  at deploy time (confirmed truthy, not blank). Between `cdk deploy` (3.3) and
  a human's `put-secret-value` (3.5), `_resolve_tavily_key` would return that
  random garbage as if it were a real key, wiring in `TavilyDiscoverer` and
  wrongly reporting `tavily_enabled=True` (every Tavily search would silently
  401, caught per-seed — no crash, but a real misreport). Confirmed via AWS
  docs that Secrets Manager's `SecretString` has a hard minimum length of 1
  (empty string is rejected outright), so a genuinely-empty secret isn't an
  option — fixed instead by pinning the secret to a fixed, recognizable
  sentinel (`TAVILY_SECRET_UNSET_SENTINEL = "UNSET-populate-via-put-secret-value"`,
  defined in both `infra/lib/agent_runtime.py` and (matching) `src/curation/
  config.py`) via `secret_string_value=SecretValue.unsafe_plain_text(...)`
  instead of `generate_secret_string`. `runtime_app._resolve_tavily_key`
  treats a resolved value equal to the sentinel the same as an empty secret
  (returns `""`, caller degrades to RSS-only). Regression coverage:
  `tests/test_infra_agent_runtime.py`'s T12 was rewritten (it previously
  asserted the buggy `GenerateSecretString` shape as *correct* — that
  assertion was what pinned the bug) to assert `GenerateSecretString` is
  **absent** and `SecretString` equals the sentinel; three new tests in
  `tests/test_runtime_app.py` cover the behavior gap end-to-end: `_resolve_
  tavily_key` returns `""` for a sentinel-valued secret,
  `_build_discoverer` (real implementation, only `boto3` mocked) stays
  RSS-only for a sentinel-valued secret, and the handler's `tavily_enabled`
  field is `False` for a sentinel-valued secret.

`uv run pytest` after both fixes: 66/66 green, 100% offline (61 prior + 2 new
Dockerfile tests + 3 new sentinel-handling tests; T12 rewritten in place, not
counted as new). `src/curation/{graph,nodes,state,interfaces}.py` re-confirmed
byte-for-byte unchanged.

## Post-audit fix #2 (2026-07-27, same day, re-audit)

- **F10 (LOW, proven exploitable — fixed):** the F2 fix introduced
  `TAVILY_SECRET_UNSET_SENTINEL` as a literal duplicated in two places
  (`infra/lib/agent_runtime.py` and `src/curation/config.py`) with only a
  code comment enforcing "must match exactly" — no test asserted they were
  actually equal. The auditor proved this via mutation testing: drifting the
  two literals apart left **all four** existing sentinel tests green while
  the deployed placeholder would silently be treated as a valid Tavily key
  again — reintroducing F2 invisibly. Fixed by adding
  `tests/test_infra_agent_runtime.py::test_infra_and_app_sentinel_literals_match`,
  which imports both constants (the `infra/`-on-`sys.path` and
  `src/`-on-`sys.path` setups coexist fine in one test process — `conftest.py`
  already adds `src/`) and asserts equality directly. Independently
  re-verified by temporarily drifting the infra literal locally: the new test
  fails loudly (`AssertionError: 'UNSET-DRIFTED-VALUE' == 'UNSET-populate-...'`)
  while every other test in the file stays green, exactly reproducing the
  auditor's mutation-test finding — then restored and reconfirmed all green.

`uv run pytest` after this fix: **67/67** green, 100% offline (66 prior + 1
new cross-boundary test). `src/curation/{graph,nodes,state,interfaces}.py`
re-confirmed byte-for-byte unchanged.

Note: F11 (spec drift — intent.md/contract.md don't describe the sentinel
design introduced by the F2 fix) is out of scope here; the coordinator has
routed it to the architect as a spec-file change.

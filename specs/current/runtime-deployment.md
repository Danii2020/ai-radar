# Runtime Deployment Specification

> Last synced: 2026-09-17. Owned artifacts: `runtime_app.py`,
> `infra/lib/agent_runtime.py`, `infra/stacks/agent_runtime_stack.py`, `Dockerfile`.

## Purpose

How the unchanged curation graph runs unattended in the cloud: packaging as
a Bedrock AgentCore Runtime agent, secret resolution, least-privilege IAM,
and — critically — the entrypoint's response-timing contract with its
caller (`scheduling`'s EventBridge Scheduler target). Kept separate from
`scheduling` because the timing/ack contract here is a property of the
Runtime entrypoint itself, reusable by any future trigger, not just
EventBridge.

## Requirements

### Requirement: RD-1 — Env-only config, graph unchanged

The Runtime entrypoint SHALL wrap the byte-for-byte unchanged compiled graph
in a `BedrockAgentCoreApp` handler that ignores its `payload` entirely;
every knob SHALL come from environment variables, so the same image
retargeted via env (e.g. a different `CARD_TABLE_NAME`) requires no rebuild.

**Source:** runtime-packaging · contract.md § Behavior Guarantees 1, 2

### Requirement: RD-2 — Runtime secret resolution, safe degradation

The Tavily API key SHALL be read from AWS Secrets Manager at invocation
time only — never baked into the image, build context, or CDK code. On
resolution failure, an empty secret, or a secret still holding the unset
sentinel placeholder, the run SHALL proceed RSS-only rather than fail.

**Source:** runtime-packaging · contract.md § Behavior Guarantees 3

#### Scenario: Secret not yet populated after a fresh deploy
- **WHEN** the execution role's secret still holds
  `TAVILY_SECRET_UNSET_SENTINEL` (the window between `cdk deploy` and the
  human's `put-secret-value`)
- **THEN** the run completes RSS-only with `tavily_enabled=False`, never
  treating the placeholder as a real key

### Requirement: RD-3 — Least privilege, scoped trust

The synthesized execution-role policy SHALL grant exactly the pinned
actions/resources (Haiku-only Bedrock, two DynamoDB actions on the table +
GSI, one secret's `GetSecretValue`, AgentCore logs + ECR pull — no
`Resource: "*"` except the required `ecr:GetAuthorizationToken`), and SHALL
be assumable only by `bedrock-agentcore.amazonaws.com` under
`aws:SourceAccount`/`aws:SourceArn` conditions.

**Source:** runtime-packaging · contract.md § Behavior Guarantees 6, 7

### Requirement: RD-4 — Immediate ack, background execution

The handler SHALL perform no network I/O or pipeline work before returning:
it allocates a `run_id`, registers an async task, schedules the background
coroutine, and returns in sub-second wall-clock time — independent of
pipeline duration — so a caller with a synchronous response-timeout (e.g.
EventBridge Scheduler's ~30s `Universal` target) never sees a timeout on a
healthy long-running curation pass.

**Source:** async-invocation-ack · contract.md § Behavior Guarantees 1, 2

#### Scenario: A curation run takes longer than a caller's timeout
- **WHEN** a caller with a ~30s synchronous response timeout invokes the
  agent and the curation pass takes 25–35s
- **THEN** the caller receives an ack (`{"status": "accepted", "run_id": …}`)
  in under a second, and the full pipeline still runs to completion as a
  background task

### Requirement: RD-5 — Single-flight per process

While a run is active, a further invocation on the same process SHALL
return `{"status": "already_running", "run_id": <that id>}` with HTTP 200
and start no second pipeline.

**Source:** async-invocation-ack · contract.md § Behavior Guarantees 4

### Requirement: RD-6 — Run results relocated to a CloudWatch record

The ack response SHALL NOT carry the run's counts; those SHALL appear in a
`curation_run_complete` CloudWatch log record, joined to the ack by
`run_id`. This is a deliberate, documented regression in operator
ergonomics, not an oversight.

**Source:** async-invocation-ack · contract.md § Behavior Guarantees 7

## Invariants

1. `bedrock_agentcore`, `asyncio`, and the Secrets Manager `boto3` client
   are confined to `runtime_app.py` (the composition root) — `src/curation/**`
   stays synchronous and liftable onto other infra (runtime-packaging BG1,
   async-invocation-ack BG8).
2. An exception anywhere in the pipeline is caught, logged as
   `curation_run_failed`, and never becomes an unhandled 5xx or a stuck
   single-flight guard — the guard is always released in a `finally`
   (async-invocation-ack BG5).

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| runtime-packaging | 2026-07-27 | `BedrockAgentCoreApp` entrypoint, execution-role CDK stack, Secrets Manager Tavily resolution, `uv`-based Dockerfile. |
| async-invocation-ack | 2026-08-10 | Async handler with immediate ack + background execution, single-flight guard — fixes `scheduling`'s finding F5 (EventBridge Scheduler's undocumented ~30s synchronous target timeout). |

## Related ADRs

None yet — both contributing features shipped before `harny-adr` existed in
this project.

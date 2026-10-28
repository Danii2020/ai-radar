# Runtime Deployment Specification

> Last synced: 2026-10-28. Owned artifacts: `runtime_app.py`, `chat_app.py`,
> `infra/lib/agent_runtime.py`, `infra/stacks/agent_runtime_stack.py`,
> `infra/lib/chat_runtime.py`, `infra/stacks/chat_runtime_stack.py`, `Dockerfile`,
> `scripts/ci/agentcore.template.yaml` and `scripts/ci/agentcore_config.py` (the CI render of the agent config).

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
actions/resources (Haiku-only Bedrock, plus `bedrock:InvokeModel` on the Titan v2
foundation-model ARN alone, two DynamoDB actions on the table + GSI, one secret's
`GetSecretValue`, AgentCore logs + ECR pull — no `Resource: "*"` except the required
`ecr:GetAuthorizationToken`), and SHALL be assumable only by
`bedrock-agentcore.amazonaws.com` under `aws:SourceAccount`/`aws:SourceArn`
conditions. Each model gets its own pinned statement; the Haiku statement stays
Haiku-only.

**Source:** runtime-packaging · contract.md § Behavior Guarantees 6, 7; amended by chat-retrieval · execution-plan.md § Proposed approach (`InvokeTitanEmbed` statement)

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

### Requirement: RD-7 — A second agent gets its own separate, least-privilege role

The system SHALL give the chat agent (`chat_app.py`) its own execution role in its own CDK
construct and stack (`AiRadarChatRuntime`), with exactly the chat's statements: model
invokes for Sonnet 4.6 and Titan v2, `dynamodb:Query` on the `feed-by-score` index only,
the AgentCore log writes, and ECR pull. Its trust policy SHALL allow only
`bedrock-agentcore.amazonaws.com`, conditioned on `aws:SourceAccount` and `aws:SourceArn`.
The curation role SHALL NOT be widened to serve the chat agent.

**Source:** chat-agent-runtime · execution-plan.md § Proposed approach (Decision (IAM)); intent.md § AC7

#### Scenario: The chat role is synthesized for the chat agent only
- **WHEN** the CDK app is synthesized
- **THEN** `AiRadarChatRuntime` holds seven inline statements, none with a write action, a table-level ARN, `dynamodb:Scan`, or a Haiku or secret grant; and `AiRadarRuntimeRole`'s statement set is unchanged by chat-agent-runtime

### Requirement: RD-8 — One shared Dockerfile selects the entrypoint by environment

The root `Dockerfile` SHALL run `${AGENT_ENTRYPOINT:-runtime_app.py}` as its CMD (through
`exec`, so the Python process is PID 1). With no setting it SHALL run the curation entrypoint
unchanged. The chat agent SHALL be deployed with `AGENT_ENTRYPOINT=chat_app.py`. Each agent
keeps its own image tag and AgentCore Runtime. A second Dockerfile SHALL NOT be added to the
agent source tree, because the toolkit builds only the one at the `source_path`.

**Source:** chat-agent-runtime · execution-plan.md § Proposed approach (Decision (Docker)); § Binding constraints (toolkit `source_path` constraint); intent.md § AC8

#### Scenario: The chat agent is deployed without the flag
- **WHEN** the chat agent's runtime is started without `AGENT_ENTRYPOINT=chat_app.py`
- **THEN** the image runs the curation entrypoint, and the chat invoke returns the curation ack rather than an answer (the runbook's AC10 step 6 check catches this)

### Requirement: RD-9 — CI deploys both agents in place, from the root Dockerfile

The system SHALL deploy the two existing agent runtimes from CI with `agentcore deploy -a <agent> --local-build`,
from an agent config rendered in the runner that carries each existing runtime id, so the toolkit updates the
runtime and never creates one. Before each deploy, the deploy job SHALL copy the root `Dockerfile`, unchanged,
into `.bedrock_agentcore/<agent>/Dockerfile` beside the rendered config, because the locked toolkit reads it
only from that path. The chat agent SHALL always get `AGENT_ENTRYPOINT=chat_app.py` (RD-8). No second Dockerfile
SHALL be committed.

**Source:** backend-cicd-pipeline · execution-plan.md § Proposed approach (agents; ADR 0044); § Binding constraints (agent Dockerfile placement); intent.md § AC6

#### Scenario: The copy step is missing for one agent
- **WHEN** the deploy job has no copy step for `ai_radar_chat`
- **THEN** the offline workflow test fails (`tests/test_ci_workflows.py -k dockerfile`). The live agent deploy
  that keeps both runtime ids is pending O12 e, so this is not yet verified live

## Invariants

1. `bedrock_agentcore`, `asyncio`, and the Secrets Manager `boto3` client
   are confined to the root entrypoints, `runtime_app.py` (curation) and `chat_app.py`
   (chat), which are the composition roots — `src/curation/**` stays synchronous and
   liftable onto other infra (runtime-packaging BG1, async-invocation-ack BG8;
   chat-agent-runtime extends the confinement to `chat_app.py`, ADR 0016).
2. An exception anywhere in the pipeline is caught, logged as
   `curation_run_failed`, and never becomes an unhandled 5xx or a stuck
   single-flight guard — the guard is always released in a `finally`
   (async-invocation-ack BG5).

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| runtime-packaging | 2026-07-27 | `BedrockAgentCoreApp` entrypoint, execution-role CDK stack, Secrets Manager Tavily resolution, `uv`-based Dockerfile. |
| async-invocation-ack | 2026-08-10 | Async handler with immediate ack + background execution, single-flight guard — fixes `scheduling`'s finding F5 (EventBridge Scheduler's undocumented ~30s synchronous target timeout). |
| chat-retrieval | 2026-10-13 | RD-3: the `InvokeTitanEmbed` statement (`bedrock:InvokeModel` on the Titan v2 foundation-model ARN only). The role change is in the template; the stack is not redeployed, so it is not live. |
| chat-agent-runtime | 2026-10-18 | RD-7: a second agent (`chat_app.py`) with its own `AiRadarChatRuntime` role and stack. RD-8: one shared Dockerfile with the `AGENT_ENTRYPOINT` selector, which narrows the intent's "separate Dockerfile". Invariant 1 now covers `chat_app.py`. Deployed 2026-10-18 (`ai_radar_chat-JFCO0R9lkT`). |
| backend-cicd-pipeline | 2026-10-28 | RD-9: CI deploys both agents in place (`agentcore deploy -a`, local build) from the root `Dockerfile`, copied to the path the toolkit reads (ADR 0044). Implemented and audit-approved with reservations; **not live**, the agent deploy through CI is pending O12 e. |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0014](../archived/chat-retrieval/decisions/0014-titan-grant-scoped-to-the-foundation-model.md) | The Titan embedding grant is a separate statement, scoped to the one foundation-model ARN | Accepted |
| [0017](../archived/chat-agent-runtime/decisions/0017-one-shared-dockerfile-with-entrypoint-selected-by-environment.md) | One root Dockerfile serves both agents, with the entrypoint selected by AGENT_ENTRYPOINT | Accepted |
| [0020](../archived/chat-agent-runtime/decisions/0020-chat-execution-role-is-a-separate-least-privilege-construct.md) | The chat agent gets its own execution role, in its own CDK construct and stack, and the curation role is not widened | Accepted |
| [0044](../archived/backend-cicd-pipeline/decisions/0044-agents-built-locally-from-a-copy-of-the-root-dockerfile.md) | The agents are deployed with a local build, from a copy of the root Dockerfile placed where the toolkit reads it | Accepted |

(Both earlier contributing features shipped before `harny-adr` existed in this project, so they get no retroactive ADRs.)

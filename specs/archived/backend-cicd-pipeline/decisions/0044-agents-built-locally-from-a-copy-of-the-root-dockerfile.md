# ADR 0044: The agents are deployed with a local build, from a copy of the root Dockerfile placed where the toolkit reads it

- **Status**: Accepted
- **Date**: 2026-10-28
- **Feature**: backend-cicd-pipeline
- **Capability**: runtime-deployment
- **Source**: execution-plan.md § Proposed approach (Decision (agents, ADR candidate 0044), including its revision-3 Consequence on the Dockerfile copy step); § Binding constraints (Agent Dockerfile placement, AC6, audit F1; CI never reads or writes the local config); § Risks (toolkit layout change)
- **Trigger**: (a) it chooses `--local-build` on a native arm64 runner over the toolkit's default CodeBuild path, over `boto3` `UpdateAgentRuntime` and over `source_path: null`; (b) it couples the deploy job to the toolkit's build-artifact layout, which later toolkit releases may move

## Context
Both agents are built from the one root `Dockerfile` (RD-8, ADR 0017). The toolkit's default build path runs in CodeBuild. It needs the deploy role to create an IAM role, an S3 bucket and a CodeBuild project, which widens the deploy role. The human runbook uses that CodeBuild path. The `--local-build` path builds on the runner, which has the same architecture as the image, but it resolves the Dockerfile differently. In the locked toolkit 0.3.10, `agentcore deploy --local-build` reads `get_agentcore_directory(<config dir>, <agent>, source_path)/Dockerfile`. With `source_path` set, that is `<config dir>/.bedrock_agentcore/<agent>/Dockerfile`, and it fails with "Dockerfile not found" when the file is absent. That directory is gitignored, so a CI checkout does not have it (audit round 1, F1).

## Decision
The deploy job runs `agentcore deploy -a <agent> --local-build --auto-update-on-conflict --image-tag <short sha>` on an arm64 runner, from a config rendered in the runner (`scripts/ci/agentcore.template.yaml`), which carries each existing runtime id. Before each `agentcore deploy`, the job runs `mkdir -p` on `.bedrock_agentcore/<agent>/` and copies the root `Dockerfile` into it unchanged, for both `ai_radar_curation` and `ai_radar_chat`. The renderer's contract and `source_path` are unchanged, and the build context stays the repository root. No second Dockerfile is committed. The chat agent always gets `--env AGENT_ENTRYPOINT=chat_app.py`. The human's CodeBuild runbook remains valid, and both paths build the same root `Dockerfile`.

## Alternatives considered
| Option | Why not |
|---|---|
| The toolkit's default CodeBuild build | It calls `iam:CreateRole`, `s3:CreateBucket` and `codebuild:CreateProject` when those are missing, which widens the deploy role and creates a toolkit-owned role. |
| `boto3` `UpdateAgentRuntime` directly | It re-implements the toolkit and diverges from the human runbook. |
| `source_path: null` | It contradicts the binding constraint and the toolkit's multi-agent layout (ADR 0017). |
| The renderer writes the Dockerfile copy | It changes the renderer's contract that its output directory holds only the YAML. |
| Commit `.bedrock_agentcore/<agent>/Dockerfile` copies | Two more Dockerfiles that drift from the root one, against RD-8. |

## Consequences
**Positive**: the deploy role needs no CodeBuild, S3 or IAM-create permission for the agents. Both agents are built from the same root `Dockerfile` as the human path. Each image is tagged with the commit's short sha, which gives the rollback a target.
**Accepted costs**: CI now depends on the toolkit's private build-artifact layout (`get_agentcore_directory`). A toolkit release can move that path. The `uv.lock` pin (0.3.10) and an offline test that computes the path with the toolkit's own `get_agentcore_directory` catch such a move at the toolkit bump, not at deploy time. The copy step must stay before every `agentcore deploy`, and the workflow test fails if it is removed, placed late or missing for one agent. A first deploy updates both Lambda images once, because CI's asset hashes differ from the laptop's (expected, not a defect). The agent deploy itself is not yet run live (tasks O12 e).

## Follow-ups
- On any toolkit bump, re-run the offline Dockerfile-placement test (`-k dockerfile`) before merging.
- Watch the first live deploy for the deploy role's `AccessDenied` on any toolkit call (tasks O12 h).

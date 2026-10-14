# ADR 0014: The Titan embedding grant is a separate statement, scoped to the one foundation-model ARN

- **Status**: Accepted
- **Date**: 2026-10-13
- **Feature**: chat-retrieval
- **Capability**: runtime-deployment
- **Source**: execution-plan.md § Proposed approach (decision: `agent_runtime.py` adds an `InvokeTitanEmbed` statement); § Binding constraints (RD-3 pinned resources)
- **Trigger**: (b) it sets the rule that each model gets its own pinned statement; (d) it accepts that the grant is not live until the role is redeployed

## Context
The curation runtime now calls Titan v2 to embed cards. The execution role is least-privilege by design (RD-3): the Haiku statement is Haiku-only, and every resource is pinned. Titan is invoked by its plain model id in this code, not through an inference profile.

## Decision
Add a separate `InvokeTitanEmbed` statement granting `bedrock:InvokeModel` on `arn:aws:bedrock:<region>::foundation-model/amazon.titan-embed-text-v2:0` only. The Haiku statement is unchanged and stays Haiku-only.

## Alternatives considered
| Option | Why not |
|---|---|
| Widen the Haiku statement to include Titan | Mixes two models in one statement and forces the Haiku-only test to be weakened. |
| Wildcard `foundation-model/*` | Grants every foundation model in the region, which breaks RD-3's pinned-resource rule. |

## Consequences
**Positive**: least privilege holds. A future model needs its own pinned statement and its own test.
**Accepted costs**: the grant is not live in AWS yet. `AiRadarRuntimeRole` must be redeployed first (pending deploy step 1). The infra tests check the synthesized template, not the deployed role.

## Follow-ups
- The chat runtime's `dynamodb:Query` grant on `feed-by-score` belongs to the later chat-runtime spec.

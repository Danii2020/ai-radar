# ADR 0020: The chat agent gets its own execution role, in its own CDK construct and stack, and the curation role is not widened

- **Status**: Accepted
- **Date**: 2026-10-18
- **Feature**: chat-agent-runtime
- **Capability**: runtime-deployment
- **Source**: execution-plan.md § Proposed approach (Decision (IAM)); § Binding constraints (the chat role is separate and grants `dynamodb:Query` on the `feed-by-score` index ARN only); intent.md § AC7
- **Trigger**: (a) it chooses between adding statements to the existing curation role and a separate construct; (b) it sets the rule that a read-only agent gets its own role, with an index-only grant

## Context
Two agents now run under AgentCore Runtime. The curation role can write to the card table and holds a secret grant, while the chat agent only reads. The intent (AC7) requires the chat role to grant exactly the model invokes, `dynamodb:Query` on the `feed-by-score` index with no table-level or write action, the AgentCore logs, and ECR pull. It must be assumable only by `bedrock-agentcore.amazonaws.com` under `aws:SourceAccount` and `aws:SourceArn`. The curation role must not be widened for chat.

## Decision
`ChatRuntime` (`infra/lib/chat_runtime.py`) is a separate construct in its own stack, `AiRadarChatRuntime`. It mirrors the curation role's trust policy and statement style, and it holds exactly seven statements: `InvokeSonnetCrossRegion`, `InvokeTitanEmbed`, `CardIndexQuery`, `AgentCoreLogsWrite`, `AgentCoreLogsDescribe`, `EcrImagePull` and `EcrAuthToken`. It has no secret grant and no write grant. Tests pin each role's exact statements.

## Alternatives considered
| Option | Why not |
|---|---|
| Add the chat statements to the curation role (`AiRadarRuntimeRole`) | It widens a role that can write to the card table and read the Tavily secret, in order to serve a read-only path. AC7 forbids this. |
| Share the statement-building code between the two constructs now | There are only two consumers. The exact-statement tests catch drift, and a shared helper would add an abstraction before a trigger fires (architecture-principles, principle 4). |

## Consequences
**Positive**: the chat role's data access is limited to a `Query` on the feed index. A compromised chat agent therefore has no table-level read or any write to the card table. The curation role is unchanged, which the diff confirms.
**Accepted costs**: the two roles repeat the trust policy and the logs and ECR statements. A change to the shared shape must be made in both places, and the tests are the only guard. The account and region are pinned as literals in the construct, as in `agent_runtime.py`, so a move to another account means changing both constructs and their tests.

## Follow-ups
- If a third agent needs the same logs and ECR statements, revisit whether to extract a shared construct.

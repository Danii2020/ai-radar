# ADR 0030: The caller's access key is long-lived and created by hand, outside CloudFormation

- **Status**: Accepted
- **Date**: 2026-10-21
- **Feature**: chat-api-auth
- **Capability**: chat-api-auth
- **Source**: execution-plan.md § Binding constraints (no `AWS::IAM::AccessKey`; the human creates the key and stores it server-side only), § Proposed approach (the rotation procedure), § Risks (the long-lived key leaks)
- **Trigger**: (a) it chooses between a stack-created `AWS::IAM::AccessKey` and a key the human creates; (d) it accepts a known cost, a long-lived secret that is rotated by hand

## Context
The web server must sign calls to the chat route, so the caller needs a credential it can use. A key created by CloudFormation would put the secret into the template, the stack and its change history. The intent forbids a secret in CloudFormation, in the repository or in logs. The caller user needs one least-privilege policy, and its key has to be created and stored by a human.

## Decision
The stack creates the IAM user `ai-radar-chat-api-caller` and its one `execute-api:Invoke` policy, and no access key, login profile or managed policy. The human runs `aws iam create-access-key --user-name ai-radar-chat-api-caller` and stores the key only in the frontend's server environment, never in a `NEXT_PUBLIC_` variable. Rotation: create the second key (a user holds at most two), switch the server environment, verify a signed 200, set the old key `Inactive`, verify again, then delete it. A suspected leak gets an immediate `Inactive`.

## Alternatives considered
| Option | Why not |
|---|---|
| A stack-created `AWS::IAM::AccessKey` | The secret would enter the template and the stack, which AC4 forbids. |
| Short-lived credentials (Vercel OIDC to an IAM role) | Named in the intent as a later spec, and out of scope here. |
| A login profile or console password for the caller | The intent forbids it. The caller has no console access. |

## Consequences
**Positive**: no secret in the repository, in CloudFormation or in logs. The audit scanned the tracked and untracked working tree and the logs, and found none.
**Accepted costs**: the key is long-lived. A leaked key lets its holder invoke the route until it is deactivated. The blast radius is one route, bounded by the throttle and the budget alert. Rotation is manual. Until the `apps/web` signing spec ships, the key stays `Active` in the local profile `ai-radar-chat-caller`.

## Follow-ups
- The `apps/web` server-side signing spec, which owns the server-only environment for the key.
- Short-lived credentials (Vercel OIDC to an IAM role) are a later spec, which would retire this key.

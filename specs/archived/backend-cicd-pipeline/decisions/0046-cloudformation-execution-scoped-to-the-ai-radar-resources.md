# ADR 0046: CloudFormation executes under two scoped customer-managed policies, not AdministratorAccess

- **Status**: Accepted
- **Date**: 2026-10-28
- **Feature**: backend-cicd-pipeline
- **Capability**: ci-cd
- **Source**: execution-plan.md § Proposed approach (Decision (scoped CloudFormation execution, ADR candidate 0046), including its revision-3 split); § Binding constraints (Scoped execution policy, Handler completeness, Resource coverage; the human decisions of 2026-10-28); § Risks (the scoped policy misses an action; a merged change creates a broad AiRadar* role); intent.md § AC13
- **Trigger**: (a) it chooses two scoped policies over `AdministratorAccess`, over a permissions boundary and over a second bootstrap for CI; (b) it constrains every later stack resource, which must have a name inside the AI Radar patterns and a handler list covered by the snapshot; (d) it accepts a residual escalation path and three reservations on unused or unverified grants

## Context
The CDK deploy role runs CloudFormation with an execution role. The default bootstrap gives that role `AdministratorAccess`. Any identity that can assume the CDK deploy role can then change anything in the account. In CI, that means any change merged to `main`. The human chose to scope the execution role to the AI Radar services and names (Q1, 2026-10-27). The committed handler snapshot lists the handler permissions of 19 resource types. The whole policy did not fit one managed policy: one policy measured 5,742 of 6,144 characters before the missing handler actions were added (audit F2). The re-bootstrap is account-wide, so it also governs the human's own `cdk deploy`.

## Decision
The CI access app defines two customer-managed policies, `cdk-exec-airadar` (data and compute services, 4,480 characters without whitespace) and `cdk-exec-airadar-2` (IAM, scheduler, budgets and every deny, 3,264 characters). Their names are outside the `AiRadar*` pattern, so their own allow statements cannot match them. The human re-bootstraps once with both ARNs. Across the two:
- every handler permission for each resource type in the seven stacks is allowed, or is in a committed omission list with a reason. The handler lists come from a committed snapshot extracted from the public CloudFormation schema zip on 2026-10-28, which the offline test reads, so it needs no network;
- each resource's physical name is matched by the resource patterns of the statements that grant its type's actions;
- `secretsmanager:GetSecretValue` is allowed only on `secret:ai-radar/tavily-api-key-*`;
- the DynamoDB item actions are allowed only on the `ai-radar-cards` table and its `feed-by-score` index;
- `dynamodb:DeleteTable` and `DeleteTableReplica` are not allowed, and an explicit deny on `ai-radar-cards` stays. The replica-removal conflict is an omission with its reason;
- `iam:CreateServiceLinkedRole` is not allowed;
- there is no `"*"` action, and IAM writes are only on `role/AiRadar*`, `policy/AiRadar*` and the caller user;
- explicit denies cover the CI roles, the OIDC provider, the `cdk-hnb659fds-*` roles and both execution policies.

Rollback is one command: re-bootstrap with `arn:aws:iam::aws:policy/AdministratorAccess`, which replaces both scoped policies.

## Alternatives considered
| Option | Why not |
|---|---|
| Keep `AdministratorAccess` | The human chose to scope it (Q1). |
| A permissions boundary on every role the stacks create | It changes every role template, which breaks AC12. Recorded as a follow-up. |
| A separate qualifier and a second bootstrap for CI | Two asset buckets and repositories, and the human's own deploys would stay admin. |
| One policy, compressed by widening patterns or actions | It trades scope for size. Rejected in the plan's revision 3. |

## Consequences
**Positive**: a merged change can act only inside the AI Radar services and names. The explicit denies stop the execution role from editing the CI access it runs under. The offline tests cover every handler permission, every physical name, the size of each policy, and the shape across both (`tests/test_infra_ci_cfn_exec_policy.py`, `tests/test_infra_ci_policy_size.py`). The audit confirmed the snapshot against the public schema (0 mismatches).
**Accepted costs**: the scoped policy also governs the human's own `cdk deploy` after the re-bootstrap. Live proof is pending: the first deploy under the policy could still hit an `AccessDenied` the snapshot did not predict (tasks O12 b, e, h). There are three reservations: unused account-level grants are on `*` (CICD-F12), the omission patterns are global wildcards (CICD-F13), and two read-only IAM user reads may be missing (CICD-F14). The residual escalation path is accepted: a merged template can still create an `AiRadar*` role with an arbitrary inline policy and trust and attach it to a Lambda or a schedule. The controls are the ruleset, `CODEOWNERS` and the PR diff. A permissions boundary is the recorded follow-up.

## Follow-ups
- Fix any `AccessDenied` seen in the first live deploy by a PR to `infra/ci_bootstrap/ci_access_stack.py`, and record it in the README (tasks O12 h).
- Decide the reservations CICD-F12 and CICD-F14 (move the unused grants to the omission list; allow the two read-only IAM actions on the caller user), as the audit recommends.
- A permissions boundary on the roles the stacks create, as a separate spec.

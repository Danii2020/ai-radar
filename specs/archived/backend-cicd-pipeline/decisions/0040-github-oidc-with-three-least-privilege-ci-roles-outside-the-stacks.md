# ADR 0040: CI authenticates with GitHub OIDC through three least-privilege roles, defined outside the deployed stacks

- **Status**: Accepted
- **Date**: 2026-10-28
- **Feature**: backend-cicd-pipeline
- **Capability**: ci-cd
- **Source**: execution-plan.md § Proposed approach (Decision (OIDC roles, ADR candidate 0040)); § Binding constraints (OIDC only, no long-lived AWS key in GitHub; no manual approval gate; deploy workflow subject); § Public repository risks
- **Trigger**: (a) it chooses three OIDC roles over one role, over IAM user keys and over deploying the roles from CI; (b) it constrains later workflows, which must use a job-scoped role with an exact `sub`, and cannot add an `environment:` without changing the deploy subject

## Context
The repository `Danii2020/ai-radar` is public, and a merge to `main` must be able to change the account. The human decided that AWS access is OIDC only and that no long-lived AWS key goes into GitHub (human decision 1, 2026-10-27). Each CI job needs a different level of access. A pull request must read the stacks and nothing more. The deploy job changes the account. The smoke job signs one request to the chat route. A fork PR must get no AWS identity at all.

## Decision
The GitHub OIDC provider and three roles are defined in the separate CDK app `infra/ci_bootstrap/`, which a human deploys once with administrator credentials and CI never deploys. The diff role trusts only `repo:Danii2020/ai-radar:pull_request` and can only assume the CDK lookup role. The deploy role trusts only `repo:Danii2020/ai-radar:ref:refs/heads/main` and can only assume the four CDK bootstrap roles plus the scoped AI Radar actions. The smoke role trusts only `main` and has `execute-api:Invoke` on the chat route. Every trust condition uses audience `sts.amazonaws.com` and `StringEquals` on the exact subject. No role grants `Action: "*"`.

## Alternatives considered
| Option | Why not |
|---|---|
| One role for every job | A pull request could then deploy. |
| IAM user access keys in GitHub | Human decision 1: no long-lived AWS key in GitHub. |
| The deploy job deploys the CI roles from CI | CI could widen its own permissions. |
| A raw CloudFormation YAML template for the roles | Equally valid, but it loses the reuse of the repository's offline synth-test style. |
| A GitHub environment with required reviewers on the deploy job | Human decision 2: no approval gate. An `environment:` also changes the OIDC subject to `…:environment:<name>`. |

## Consequences
**Positive**: a fork PR gets no OIDC token and no secret (`pull_request`, no `pull_request_target`). A PR can read the stacks through the lookup role and cannot change them. A branch other than `main` cannot assume the deploy or smoke role. The roles are offline-tested (trust, grants, names outside `AiRadar*`).
**Accepted costs**: the trust subjects name the repository and `main`. A rename of the repository or the default branch needs a PR and a human redeploy of the CI access stack. The offline tests prove the synthesized policies. The live trust is proven only by the first PR diff and the first deploy (tasks O12 d, e, f), which have not run.

## Follow-ups
- Confirm the deploy role's allow-list against CloudTrail on the first human-run deploy (tasks O12 h). The allow-list is recorded in the README.
- Consider `allowed-account-ids` on `configure-aws-credentials` as a second account guard (audit recommendation, not adopted).

# ADR 0047: Repository protection is applied by a rerunnable script that dry-runs by default

- **Status**: Accepted
- **Date**: 2026-10-28
- **Feature**: backend-cicd-pipeline
- **Capability**: ci-cd
- **Source**: execution-plan.md § Proposed approach (Decision (repository protection, ADR candidate 0047)); § Binding constraints (Repository protection, AC14); § Validation (AC14 rows); intent.md § AC14 and Q2 (the repository was not protected before this feature)
- **Trigger**: (a) it chooses a rerunnable script over classic branch protection, the Terraform GitHub provider and clicks in the UI; (b) the required check names are a contract with the workflow job names, and a test keeps them equal

## Context
`main` had no protection before this feature (Q2, 2026-10-27). The pipeline's safety depends on a ruleset that requires the PR checks, a PR for every change to `main`, and no force push. It also depends on secret scanning and push protection, a read-only default workflow token, and an approval gate for outside contributors' workflow runs. These are settings, not code, so they can drift silently if they are only set by hand.

## Decision
`scripts/ci/repo_protection.py` builds each payload with pure functions and calls `gh api` through one injectable runner. By default it prints the method, endpoint and JSON for every change, and it makes no write call. With `--apply`, it reads the current state first and writes only what differs, so a rerun changes nothing. It sets:
- a repository ruleset on `refs/heads/main`: a PR is required with 0 approvals and code-owner review off while there is one maintainer, the AC1 check jobs are required and the branch must be up to date (strict), `non_fast_forward` and `deletion` are blocked, and there are no bypass actors. It is matched by name, created when absent and updated when present;
- secret scanning and push protection, through the repository `security_and_analysis` setting;
- a read-only default workflow token that cannot approve PRs;
- an approval requirement for outside contributors' workflow runs.

A test compares the script's required check names with the workflow job names. A human reads the settings back afterwards.

## Alternatives considered
| Option | Why not |
|---|---|
| Classic branch protection | Rulesets supersede it, and they are listable as JSON. |
| The Terraform GitHub provider | A new tool and state file, for four settings. |
| Applying the settings from CI | It needs an admin token stored in GitHub. |
| Clicking the settings by hand | Undocumented and not rerunnable. The runbook names a manual step only for a setting with no API. |

## Consequences
**Positive**: the settings are reviewable in a PR, rerunnable, and checked by the read-back. A direct push to `main` is expected to be refused once the ruleset is applied; that is a live check not yet run (tasks O12 c). The check-name test catches a job rename that would otherwise leave a required check that never reports, which blocks merges, or leave nothing required.
**Accepted costs**: the script needs `gh` authenticated as an admin, which only a human has. The endpoints were checked against GitHub's REST description during the audit's round 1. The live apply, the read-back and the direct-push rejection have not run (tasks O12 c). The solo-maintainer approval count (0) is the plan's choice and is still awaiting the human's confirmation.

## Follow-ups
- Raise the approval count and turn on code-owner review when a second maintainer joins (the protection script's constants).
- Add Dependabot for the `github-actions` ecosystem so the SHA pins get updates (audit recommendation, not adopted).

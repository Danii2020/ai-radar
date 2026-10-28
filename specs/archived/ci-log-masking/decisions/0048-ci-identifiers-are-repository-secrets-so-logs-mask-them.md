# ADR 0048: The chat API id and the account id are repository secrets, so GitHub masks them in every log line

- **Status**: Accepted (amends ADR 0040; ADR 0040's file is not edited)
- **Date**: 2026-10-28
- **Feature**: ci-log-masking
- **Capability**: ci-cd
- **Source**: execution-plan.md § Proposed approach (Decision (ADR candidate 0048), and Decision (expressions)); § Binding constraints (exactly two secrets; role ARNs from the secret account and the stack names; `mask-aws-account-id` on every credentials step); intent.md § Constraints ("Contradiction with current truth, stated on purpose"); ADR 0040
- **Trigger**: (a) it chooses repository secrets over keeping the values in variables, over moving them out of `env`, over one secret per role ARN and over `mask-aws-account-id` alone; (d) it accepts that two values which are not credentials are stored as secrets, so a future reader may take them for credentials

## Context
The repository is public, so its Actions logs are public. ADR 0040 put the three role ARNs and both identifiers in repository variables, on the view that they are not credentials. That view is correct, but it does not stop them leaking. The runner prints a step's `env` block and its `with:` inputs before the step runs. A `::add-mask::` line only masks output printed after it runs. On 2026-10-28 the first live run printed the chat API id (the deploy and PR diff job logs, through the mask step's `env` block) and the account id (the `role-to-assume` input of the diff, deploy and smoke jobs). GitHub masks a repository secret from the start of the job, in every line, including `env` and `with` values and their derived strings. The intent records that the human decided to set exactly two values as secrets (2026-10-28).

## Decision
The chat API id and the account id are read only from `secrets.CHAT_API_ID` and `secrets.AWS_ACCOUNT_ID`, and no workflow references a `vars.*` context for them. Each role ARN is built as `arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/<name>`, with `<name>` equal to the stack's constant (`gha-airadar-diff`, `gha-airadar-deploy`, `gha-airadar-smoke`), which are literal in the workflow. The deploy mask step and the account guard receive the secrets through `env`. `mask-aws-account-id: true` stays on every credentials step. The five variables that held these values (`AWS_DIFF_ROLE_ARN`, `AWS_DEPLOY_ROLE_ARN`, `AWS_SMOKE_ROLE_ARN`, `AWS_ACCOUNT_ID`, `CHAT_API_ID`) are retired. The human deletes them after the merge and one clean run.

## Alternatives considered
| Option | Why not |
|---|---|
| Keep the values in variables and move them out of `env` | The `with: role-to-assume` input is printed before any step can mask it, so the account id would still leak. |
| One secret per role ARN | Three more secrets, for values that are all derived from one account id. |
| `mask-aws-account-id` alone | It masks only output printed after it runs, so the `env` and `with` lines of the first step would still show the values. |

## Consequences
**Positive**: GitHub masks both values in every log line of the `diff`, `deploy` and `smoke` jobs, including `env` blocks, `with:` inputs and the derived ARNs and URLs (the audit's round-1 review found no remaining print path before the mask). A missing secret fails closed: an empty `CHAT_API_ID` stops the deploy job before any `cdk deploy`, and an empty `AWS_ACCOUNT_ID` makes the role ARN invalid, so the credentials step fails with no AWS access. Fork PRs still get no secret, because `pull_request` does not pass secrets to forks. The static tests pin the allow-list (`GITHUB_TOKEN`, `CHAT_API_ID`, `AWS_ACCOUNT_ID`) and the secret-based ARNs.
**Accepted costs**: the two values are now stored as secrets, which is a stronger store than their status requires. Neither is a credential, since the chat route needs SigV4 (CAAUTH-2) and the account id is already in the repository. The masking is per-run: the logs of the first live run stay public until they are deleted (tasks O6). The fix is not yet committed, merged or run on GitHub, so the live check (O4, zero occurrences in the new logs) is pending. The live allow-list check is also limited: the static test matches only the dotted `secrets.NAME` form (CLM-F2). The smoke job still derives the chat id from its own stack read, and its mask stays fail-open (CICD-F10, unchanged).

## Follow-ups
- Human-only, after the fix runs once: O4 (zero-count grep of the new `diff`, `deploy` and `smoke` logs), O5 (delete the five retired variables after one clean run), O6 (delete the two leaked runs' logs for every attempt; do not re-run them).
- If Dependabot is ever enabled, its PRs read Dependabot secrets, not Actions secrets, so their `diff` job would fail closed on an empty account id. Dependabot is not adopted.
- Harden the allow-list test against `secrets['NAME']`, `toJSON(secrets)` and `secrets[` (CLM-F2). Assert the absence of `ListAgentRuntimes` (CLM-F3).

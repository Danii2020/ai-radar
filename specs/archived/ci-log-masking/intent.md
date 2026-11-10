# Intent: CI Log Masking

Shipped: 2026-10-28 (implemented and audit-approved; live O4-O6 pending)

Revision: 1
Approval: Approved (human, 2026-10-28)

## Outcome
The public GitHub Actions logs of the backend pipeline stop showing the chat API id and the AWS
account id. The first live run on 2026-10-28 showed both leaking: the chat API id in the `deploy`
and PR `diff` jobs, because the mask step's `env:` block is printed before its `::add-mask::` runs;
and the account id in the `Configure AWS credentials` step of the `diff`, `deploy` and `smoke`
jobs, because the runner prints the `role-to-assume` input taken from a repository variable. The
fix stores exactly these two values as repository secrets, which GitHub masks everywhere in a log,
and builds each role ARN from the secret account id and the fixed role name. The same change also
carries the already-verified `ecr:CreateRepository` grant that the first live agent deploy needed.

## Acceptance criteria
- **AC1** (secrets for two identifiers) The backend workflows read the chat API id only from
  `secrets.CHAT_API_ID` and the account id only from `secrets.AWS_ACCOUNT_ID`. No workflow
  references `vars.CHAT_API_ID`, `vars.AWS_ACCOUNT_ID`, `vars.AWS_DIFF_ROLE_ARN`,
  `vars.AWS_DEPLOY_ROLE_ARN` or `vars.AWS_SMOKE_ROLE_ARN`. Every `${{ }}` expression that carries
  either identifier, in any step's `env`, `with` or `run`, is a `secrets.*` reference, so no step
  puts either identifier into a log unmasked.
  Example: the deploy job's mask step has `env: CHAT_API_ID: ${{ secrets.CHAT_API_ID }}` -> the printed env block shows `***`; a workflow with `${{ vars.CHAT_API_ID }}` anywhere -> the static test fails.
- **AC2** (role ARNs from fixed names) Each job that assumes an AWS role builds the ARN as
  `arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/<name>`, with `<name>` equal to the constant in
  `infra/ci_bootstrap/ci_access_stack.py`: `gha-airadar-diff` for the PR `diff` job,
  `gha-airadar-deploy` for `deploy`, `gha-airadar-smoke` for `smoke`. Each job uses its own role.
  `mask-aws-account-id: true` stays on every credentials step.
  Example: the constant `DEPLOY_ROLE` is renamed in `ci_access_stack.py` but not in the workflow -> the static test fails; the deploy job's credentials step log shows `role-to-assume: arn:aws:iam::***:role/gha-airadar-deploy`.
- **AC3** (fail closed) The deploy job still stops before any deploy when `CHAT_API_ID` is empty,
  and the mask still precedes every `cdk deploy`. The account guard keeps its effect: it compares
  the caller account with `secrets.AWS_ACCOUNT_ID` and stops when they differ or the value is empty.
  An empty `AWS_ACCOUNT_ID` secret also makes the role ARN invalid, so the credentials step fails.
  Example: the `CHAT_API_ID` secret is unset -> the deploy job stops at the mask step; the `AWS_ACCOUNT_ID` secret is unset -> the credentials step fails, and no AWS call follows.
- **AC4** (secrets allow-list) The workflows reference no `secrets.*` other than `GITHUB_TOKEN`,
  `CHAT_API_ID` and `AWS_ACCOUNT_ID`, and never use `secrets: inherit`. The reusable checks workflow
  references no secret. This replaces `backend-cicd-pipeline` AC16's "no `secrets.*` other than
  `GITHUB_TOKEN`" (ci-cd CICD-15).
  Example: a step adds `${{ secrets.SOME_TOKEN }}` -> the static test fails.
- **AC5** (live verification) After the fix runs once, a grep of the new runs' `diff`, `deploy`
  and `smoke` job logs finds the chat API id and the account id zero times each. The two runs that
  leaked (40725880118 and 40731171201, all attempts) have their logs deleted afterwards.
  Example: `grep -cF` for each value over each downloaded job log -> `0`.
- **AC6** (ECR repository call, already implemented and verified) The deploy role may call
  `ecr:CreateRepository` only on the two agent repositories (`bedrock-agentcore-ai_radar_curation`
  and `bedrock-agentcore-ai_radar_chat`), because the locked toolkit's `deploy_to_ecr` always calls
  `create_repository` and catches `RepositoryAlreadyExistsException`. The deploy role does not get
  `bedrock-agentcore:ListAgentRuntimes`, which the toolkit does not need.
  Example: the first live deploy failed with `AccessDenied` on `ecr:CreateRepository`; with the grant, the agent deploy passed (verified live 2026-10-28); `test_deploy_role_may_call_create_repository_only_on_the_two_agent_repositories` passes.
- **AC7** (compatibility) Job names and check names are unchanged, so the repository ruleset's
  required checks still match. Fork PRs still get no secret and their diff job is still skipped.
  Deploy and smoke still run on `main` only. The smoke job keeps deriving the chat API id from its own
  stack read (it did not leak). No other repository variable is changed.

## Scope
**In**
- `.github/workflows/backend-pr.yml` and `.github/workflows/backend-deploy.yml`: the two secrets,
  the built role ARNs, the account guard source.
- Static workflow tests in `tests/test_ci_workflows.py`.
- The `ecr:CreateRepository` grant in `infra/ci_bootstrap/ci_access_stack.py` and its test (already
  implemented; recorded here, not re-specified).
- Human-only steps: create the two secrets, verify the logs, delete the five old variables, delete
  the two leaked runs' logs.
- Documentation step: README "Backend CI/CD" bootstrap step 2, `specs/current/ci-cd.md` (CICD-11,
  CICD-15, invariants, a new reservation for this live finding), and the `CLAUDE.md` pointer if needed.

**Out**
- Literals already in git history or in spec documents.
- The other repository variables.
- The `node_modules` / `.dockerignore` build speedup.
- The smoke job's fail-open mask read (open reservation CICD-F10, unchanged).
- `allowed-account-ids` on `configure-aws-credentials` and Dependabot (not adopted).

## Constraints
- The repository is public; Actions logs are public.
- Neither value is a credential: the chat route requires SigV4 (CAAUTH-2), and the account id is
  already in the repository. The goal is that public logs do not show them, as the archived AC10
  promised.
- The values are never typed into chat or committed. The human sets them with `gh secret set`, which
  reads from standard input.
- Fork PRs get no secrets on `pull_request`, and no workflow uses `pull_request_target` (CICD-2).
- **Contradiction with current truth, stated on purpose.** `ci-cd` CICD-15 says the workflows
  reference no `secrets.*` other than `GITHUB_TOKEN`, and CICD-11 says the deploy job masks from
  `vars.CHAT_API_ID`. ADR 0040 and the archived runbook put the role ARNs and both ids in repository
  variables, as "not credentials". This feature reverses that for exactly two identifiers, because a
  variable used in a step's `env` or `with` is printed before any mask applies. A new ADR records it
  and amends ADR 0040.

## Open questions
- Does `DELETE /repos/Danii2020/ai-radar/actions/runs/{id}/logs` remove the logs of every attempt of
  a re-run run? The plan verifies it by trying to download each attempt's logs afterwards; if an
  attempt's logs remain, the fallback is deleting the whole run (`DELETE .../actions/runs/{id}`),
  which the human decides then.
- If Dependabot is ever enabled, its PRs read Dependabot secrets, not Actions secrets, so their diff
  job would fail on an empty account id. Not a problem today (Dependabot is not adopted).

## Revision history
- Revision 1 (2026-10-28): first draft, from the first live run's findings and the human's decision.

# Tasks: CI Log Masking

## Status
Implemented and audit-approved with reservations (round 1, 2026-10-28; all reservations accepted by the human).
Documented and archived 2026-10-28. NOT committed, merged or run on GitHub. Live steps O4, O5 and O6 are human-only and pending.

## Baseline
- Base commit: ff8d56d (Merge pull request #11 from Danii2020/feat/backend-cicd-pipeline)
- Branch: fix/ci-deploy-ecr-createrepository (carries the uncommitted AC6 change in
  `infra/ci_bootstrap/ci_access_stack.py` and `tests/test_infra_ci_bootstrap.py`)
- Interpreter: Python 3.12.11 (uv 0.7.17)
- Cwd: /Users/danielerazo/python/project-agentcore-app
- Commands: `uv run pytest tests/ -q`; `uv run ruff check .`; `uv run mypy .`
- Pre-existing failures: none recorded. The pre-change baseline (O8, before O2) was 827 passed plus 8 intended red tests.

## Outcomes
- [x] **O1** (AC6): Deploy role may call `ecr:CreateRepository` on the two agent repositories only;
  no `bedrock-agentcore:ListAgentRuntimes`; a pyright-only ignore comment in `ci_access_stack.py`.
  - Tests: `tests/test_infra_ci_bootstrap.py::test_deploy_role_may_call_create_repository_only_on_the_two_agent_repositories`
  - Red: the first live agent deploy failed with `AccessDenied` on `ecr:CreateRepository` (2026-10-28)
  - Green: the test passes, and the live agent deploy passed with the grant (2026-10-28, reported by the coordinator)
- [x] **O2** (AC1, AC2, AC3, AC4, AC7): Workflows read `secrets.CHAT_API_ID` and
  `secrets.AWS_ACCOUNT_ID`; role ARNs built from the secret account id and the stack's role names;
  account guard and deploy mask from the secrets; no `vars.*` for the five retired names.
  - Tests: `tests/test_ci_workflows.py`. New: `test_no_workflow_references_the_retired_repository_variables`,
    `test_ids_reach_steps_only_through_secrets` (+ 4 `test_ids_detector_*` fixture tests),
    `test_role_arns_are_built_from_the_secret_account_and_the_stack_role_names`,
    `test_account_guard_compares_with_the_secret_and_fails_on_empty` (runs the guard script with a shimmed `aws`),
    `test_smoke_job_does_not_read_the_chat_api_id_secret`, `test_the_reusable_checks_workflow_references_no_secret`.
    Changed (renamed where the old name said "variable"): the module docstring;
    `test_diff_job_assumes_the_diff_role_built_from_the_secret_account_and_is_the_only_job_with_an_id_token`,
    `test_deploy_trigger_deploy_job_authenticates_through_oidc_with_the_built_deploy_role`,
    `test_smoke_job_uses_its_own_oidc_role_distinct_from_the_deploy_role`,
    `test_workflows_reference_only_allow_listed_secrets_and_never_inherit` (was `test_no_workflow_references_a_secret_other_than_the_github_token`),
    `_mask_deploy_problems` and its tests `test_mask_deploy_job_masks_from_the_secret_and_fails_closed`,
    `test_mask_deploy_detector_*` (the "does not use the secret" one renamed; one new case for stop-on-empty)
  - Red: 2026-10-28, 8 fail against the current `vars.*` workflows: the three role tests and
    `test_role_arns_...` (`'${{ vars.AWS_DIFF_ROLE_ARN }}'` does not match `arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/gha-airadar-diff`, and the deploy and smoke equivalents),
    `test_mask_deploy_job_masks_from_the_secret_and_fails_closed` (`no mask step uses secrets.CHAT_API_ID`),
    `test_no_workflow_references_the_retired_repository_variables` (`backend-deploy.yml: vars.AWS_DEPLOY_ROLE_ARN`),
    `test_ids_reach_steps_only_through_secrets` (`deploy[5].with: vars.AWS_DEPLOY_ROLE_ARN does not come from the two secrets`, 4 problems),
    `test_account_guard_compares_with_the_secret_and_fails_on_empty` (`secrets.AWS_ACCOUNT_ID` absent, the guard's env is `vars.AWS_ACCOUNT_ID`).
    Green today by design: allow-list, checks-has-no-secret, smoke-has-no-CHAT_API_ID, and the fixture/detector tests.
    Satisfiability checked: a copy of the workflows with the five `vars.*` replaced by the secrets and the built ARNs makes all of them pass
  - Green: 2026-10-28 (executor): `backend-pr.yml` and `backend-deploy.yml` now build the three role ARNs from `secrets.AWS_ACCOUNT_ID` and `gha-airadar-diff|deploy|smoke`, and read `secrets.AWS_ACCOUNT_ID` (account guard) and `secrets.CHAT_API_ID` (PR diff job, deploy mask step, still fail-closed). The smoke job is unchanged apart from its role ARN and keeps deriving the id from AWS. `uv run pytest tests/test_ci_workflows.py -q`: 72 passed
- [x] **O3** Human-only, BEFORE the PR opens: `gh secret set CHAT_API_ID` and
  `gh secret set AWS_ACCOUNT_ID` (values from standard input, never typed into chat or committed);
  confirm with `gh secret list` (names only).
  - Done 2026-10-28 (human). Evidence: `gh secret list` names and timestamps only. The values were never seen by the executor.
- [x] **O7** Docs: README "Backend CI/CD" bootstrap step 2 (two secrets, role ARNs no longer
  variables); `specs/current/ci-cd.md` CICD-11, CICD-15, invariants, a new reservation for the live
  finding; ADR 0048 in the registry; the `CLAUDE.md` pointer if needed.
  - Done 2026-10-28 (documentation step): README step 1 and step 2 rewritten, with the leak note and the cleanup steps; `ci-cd.md` CICD-10, CICD-11, CICD-15, invariants 6 and 7, reservations CICD-LEAK and CLM-F2..F4, and the Docker-cache open note; ADR 0048 registered; CHANGELOG and `CLAUDE.md` updated.
- [ ] **O4** Human-only, after the PR's diff run and after the merge's first deploy run: verify AC5 by
  grepping the new runs' `diff`, `deploy` and `smoke` job logs for each value (expect 0 each),
  using the same method as on 2026-10-28. Pending: not run yet.
- [ ] **O5** Human-only, after the merge and one successful deploy run: delete the five unused
  variables with `gh variable delete AWS_DIFF_ROLE_ARN`, `AWS_DEPLOY_ROLE_ARN`, `AWS_SMOKE_ROLE_ARN`,
  `AWS_ACCOUNT_ID`, `CHAT_API_ID`; confirm with `gh variable list`. Pending: not run yet.
- [ ] **O6** Human-only, after the fix has run once: delete the leaked logs of runs 40725880118 and
  40731171201, all attempts (`gh api -X DELETE repos/Danii2020/ai-radar/actions/runs/<id>/logs`);
  try to download each attempt's logs afterwards and record that none remain (intent open question).
  Pending: not run yet. Do not re-run those two runs.
- [x] **O8** Broader suite vs baseline: `uv run pytest tests/ -q`, `uv run ruff check .`, `uv run mypy .`.
  - Result 2026-10-28 (executor, after O2): 835 passed, ruff clean, mypy clean (122 files). actionlint 1.7.12 with shellcheck 0.11.0 over all five workflow files: exit 0, no findings. Baseline before O2: 827 passed, 8 intended red.
- [x] **O9** Independent audit: round 1, 2026-10-28, APPROVED WITH RESERVATIONS (`audit.md`). F1 is fixed by this refresh. F2, F3 and F4 are accepted by the human as reservations (`specs/current/ci-cd.md`, CLM-F2..F4).

## Working state
- Updated: 2026-10-28
- Outcome: O1, O2, O3, O7, O8, O9 done; O4, O5, O6 human-only and pending
- Phase: implemented, audit-approved with reservations, documented, archived. Not committed, merged or run on GitHub.
- In progress: —
- Last command: —
- Next step: commit and merge by the human; then O4 after the first run of the new diff, deploy and smoke jobs; O5 after one clean deploy run; O6 after the fixed workflow has run once (do not re-run the two leaked runs).

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| F1 (LOW, stale tasks.md) | Fixed by this refresh: Status, Baseline, Working state and Checkpoint are current. O3, O7 and O9 are ticked with evidence. O4–O6 stay unticked. | this file |
| F2 (LOW, allow-list test matches only the dotted form) | Accepted as-is by the human (CLM-F2 in `ci-cd.md`). Not changed. | audit round 1 |
| F3 (LOW, no negative assertion for ListAgentRuntimes) | Accepted as-is by the human (CLM-F3 in `ci-cd.md`). Not changed. | audit round 1 |
| F4 (LOW, live AC5 not run) | Pending by design: O4 and O6 are human-only and not run. Recorded as CLM-F4 and CICD-LEAK in `ci-cd.md`. | audit round 1 |

## Checkpoint
Implemented and audit round 1 APPROVED WITH RESERVATIONS (2026-10-28). Documented and archived 2026-10-28.
Not committed, merged or run on GitHub. Resume with the human-only steps: O4 after the first run of the new
jobs, O5 after one clean deploy run, O6 after the fixed workflow has run once.

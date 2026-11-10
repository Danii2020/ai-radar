# Execution Plan: CI Log Masking

## Guidance consulted
- `CLAUDE.md` (two harness roots, live AWS steps are human-only, the uv-only rule).
- `harny-sync` lookup: `specs/current/_index.md` (next ADR **0048**), `specs/current/ci-cd.md`
  (CICD-2, CICD-3, CICD-11, CICD-15, invariants, CICD-F10, CICD-F11), `specs/current/chat-api-auth.md`
  (CAAUTH-2, CAAUTH-10, CAAUTH-SMOKE).
- ADR 0040 (`specs/archived/backend-cicd-pipeline/decisions/0040-*.md`).
- `.github/workflows/backend-pr.yml` (diff role from `vars.AWS_DIFF_ROLE_ARN`; mask from
  `vars.CHAT_API_ID`, tolerant of empty) and `.github/workflows/backend-deploy.yml` (deploy and smoke
  roles from `vars.AWS_*_ROLE_ARN`; account guard from `vars.AWS_ACCOUNT_ID`; mask from
  `vars.CHAT_API_ID`, fails on empty).
- `infra/ci_bootstrap/ci_access_stack.py` (constants `DIFF_ROLE`, `DEPLOY_ROLE`, `SMOKE_ROLE`; the
  uncommitted `ecr:CreateRepository` grant and pyright-only ignore on this branch).
- `tests/test_ci_workflows.py` (the tests that pin `vars.*`, listed under Consumers),
  `tests/test_infra_ci_bootstrap.py` (`test_deploy_role_may_call_create_repository_only_on_the_two_agent_repositories`).
- README "Backend CI/CD" bootstrap step 2 (sets the five variables).
- The coordinator's live findings of 2026-10-28 (log greps of the deploy, smoke and diff jobs).

## Ownership
- `.github/workflows/backend-pr.yml`, `.github/workflows/backend-deploy.yml`.
- `tests/test_ci_workflows.py`.
- Already done on this branch: `infra/ci_bootstrap/ci_access_stack.py`, `tests/test_infra_ci_bootstrap.py`.
- Affected `specs/current` capabilities: `ci-cd` (CICD-11, CICD-15, invariants, reservations). Not
  `chat-api-auth`: the route and its principals do not change.

## Binding constraints
- Exactly two repository secrets, `CHAT_API_ID` and `AWS_ACCOUNT_ID`; no other new secret (human
  decision, 2026-10-28).
- Role ARNs are `arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/<name>`, with the names equal to
  `DIFF_ROLE`, `DEPLOY_ROLE` and `SMOKE_ROLE` in `infra/ci_bootstrap/ci_access_stack.py`. The role
  names are not secret and stay literal in the workflow.
- `mask-aws-account-id: true` stays on every `configure-aws-credentials` step.
- The deploy job's mask step keeps failing on an empty `CHAT_API_ID` and keeps preceding every
  `cdk deploy`; its stack read keeps failing closed (CICD-11). The PR job's mask stays tolerant of an
  empty value (the diff prints no URL by itself).
- The account guard keeps its logic and only changes its source to `secrets.AWS_ACCOUNT_ID`.
- No job or check name changes (the ruleset's required checks, CICD-13).
- Secrets are never passed to the reusable checks workflow, and `secrets: inherit` stays forbidden.
- The secret values are never committed, echoed or typed into chat.

## Proposed approach
Revisable by the executor if it records why.
- **Decision (ADR candidate 0048):** store the two non-credential identifiers as repository secrets
  so GitHub masks them in every log line, including env blocks, `with:` inputs and expanded `run`
  text, and build the role ARNs from the secret account id plus the fixed role names. This amends
  ADR 0040 (which put the role ARNs in variables) and ci-cd CICD-11 and CICD-15. — rationale:
  `::add-mask::` only masks output after it runs, and the runner prints a step's `env` and `with`
  before that; secrets are masked from the start. Rejected: keeping variables and moving the values
  out of `env` (the `with: role-to-assume` input is printed before any step can mask it); one secret
  per role ARN (three more secrets for values derived from one); `mask-aws-account-id` alone (masks
  only later output).
- **Decision (expressions):** pass the secrets through `env` where a shell needs them (the mask
  step, the account guard) and directly in `with: role-to-assume`. The PR diff's `sed` substitution
  keeps reading `CHAT_API_ID` from the step's env.
- The ECR grant (AC6) is already implemented and verified; no further change.

## Consumers and migration
- Existing tests in `tests/test_ci_workflows.py` that change:
  - module docstring line "AWS roles are chosen with `${{ vars.* }}` …, never secrets";
  - `test_diff_job_assumes_a_repository_variable_role_and_is_the_only_job_with_an_id_token` (asserts
    `vars.` in, and `secrets.` not in, the role expression);
  - `test_deploy_trigger_deploy_job_authenticates_through_oidc_with_a_variable_role` (same);
  - `test_smoke_job_uses_its_own_oidc_role_distinct_from_the_deploy_role` (`vars.` assertion; the
    distinctness assertion stays);
  - `test_no_workflow_references_a_secret_other_than_the_github_token` (the allow-list becomes
    `GITHUB_TOKEN`, `CHAT_API_ID`, `AWS_ACCOUNT_ID`; the `secrets: inherit` check stays);
  - `_mask_deploy_problems` and `test_mask_deploy_job_masks_from_the_repository_variable_and_fails_closed`,
    `test_mask_deploy_detector_accepts_a_correct_step`, `test_mask_deploy_detector_flags_a_swallowed_read_error`,
    `test_mask_deploy_detector_flags_a_mask_that_does_not_use_the_variable`,
    `test_mask_deploy_detector_flags_a_mask_placed_after_the_deploy` (`vars.CHAT_API_ID` becomes
    `secrets.CHAT_API_ID`, in the detector and its fixtures).
- Unchanged: `test_deploy_trigger_account_check_precedes_the_first_cdk_or_agentcore_step` (order only),
  the ruleset check-name cross-check, every other test.
- Repository variables `AWS_DIFF_ROLE_ARN`, `AWS_DEPLOY_ROLE_ARN`, `AWS_SMOKE_ROLE_ARN`,
  `AWS_ACCOUNT_ID`, `CHAT_API_ID`: unused after the merge, deleted by the human (tasks O5).
- Docs (documentation step): README "Backend CI/CD" bootstrap step 2 (two secrets with
  `gh secret set`; the role ARNs are no longer variables; the stale-`CHAT_API_ID` note now applies to
  the secret); `specs/current/ci-cd.md` CICD-11 (mask from `secrets.CHAT_API_ID`), CICD-15 (the new
  allow-list), an invariant (no `vars.*` for the five names; role names equal the stack constants), a
  new reservation for this live finding and its closure; the ADR registry entry 0048; the `CLAUDE.md`
  pointer only if it mentions the variables.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A secret is unset when the PR's own diff runs, so the diff leaks nothing but fails | Med | Low | The human creates both secrets before opening the PR (tasks O3). |
| The variables are deleted before the merge, breaking `main`'s current workflow | Low | Med | Delete only after the merge and one successful run (tasks O5). |
| GitHub stops masking a secret that appears in a transformed form (for example URL-encoded or split) | Low | Low | The values appear only verbatim; the live grep (AC5) checks the real logs. |
| Leaked logs remain in a run attempt | Med | Low | Download each attempt's logs after the DELETE and confirm they are gone (intent open question). |
| A role rename in the stack is not mirrored in the workflow | Low | Med | AC2 test compares with the stack constants. |
| Public-repo register: the two values become secrets, so a future reader may treat them as credentials | Low | Low | The README and ADR 0048 say they are identifiers kept secret only for log masking. |

## Validation
One row per AC. All commands run from the repo root. Static tests parse the workflow YAML with
PyYAML, as today; no new tier or setup.

| AC | Demonstrated by | Tests to write | Tier | Framework | Setup | Focused command | Broader command | Cwd |
|---|---|---|---|---|---|---|---|---|
| AC1 | No backend workflow references `vars.CHAT_API_ID`, `vars.AWS_ACCOUNT_ID` or `vars.AWS_{DIFF,DEPLOY,SMOKE}_ROLE_ARN`; every `${{ }}` expression naming `CHAT_API_ID` or `AWS_ACCOUNT_ID` in any step's `env`, `with` or `run` is a `secrets.*` reference; failure cases: a fixture step with `${{ vars.CHAT_API_ID }}` in `env`, and one with `${{ vars.AWS_DEPLOY_ROLE_ARN }}` in `with`, each fail | new `test_no_workflow_references_the_retired_repository_variables`, new `test_ids_reach_steps_only_through_secrets` (with fixtures) | unit (static YAML) | pytest + PyYAML | none | `uv run pytest tests/test_ci_workflows.py -q -k "retired or only_through_secrets"` | `uv run pytest tests/ -q` | repo root |
| AC2 | Each of `diff`, `deploy`, `smoke` has `role-to-assume` equal to `arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/<name>`, with `<name>` imported from `ci_bootstrap.ci_access_stack` (`DIFF_ROLE`, `DEPLOY_ROLE`, `SMOKE_ROLE`); the three differ; `mask-aws-account-id: true` on every credentials step | new `test_role_arns_are_built_from_the_secret_account_and_the_stack_role_names`; changed `test_diff_job_…`, `test_deploy_trigger_deploy_job_authenticates_…`, `test_smoke_job_uses_its_own_oidc_role_…` | unit (static YAML) | pytest + PyYAML | none | `uv run pytest tests/test_ci_workflows.py -q -k "role"` | `uv run pytest tests/ -q` | repo root |
| AC3 | The deploy mask reads `secrets.CHAT_API_ID`, stops on empty, fails closed on the stack read, and precedes every `cdk deploy`; the account guard reads `secrets.AWS_ACCOUNT_ID` and exits non-zero when it is empty or differs | changed `_mask_deploy_problems` and its five tests; new `test_account_guard_compares_with_the_secret_and_fails_on_empty` | unit (static YAML) | pytest + PyYAML | none | `uv run pytest tests/test_ci_workflows.py -q -k "mask_deploy or account_guard"` | `uv run pytest tests/ -q` | repo root |
| AC4 | The set of `secrets.*` names across the backend workflows is a subset of `{GITHUB_TOKEN, CHAT_API_ID, AWS_ACCOUNT_ID}`; `backend-checks.yml` has none; no `secrets: inherit` | changed `test_no_workflow_references_a_secret_other_than_the_github_token` (renamed to reflect the allow-list) | unit (static YAML) | pytest + PyYAML | none | `uv run pytest tests/test_ci_workflows.py -q -k secret` | `uv run pytest tests/ -q` | repo root |
| AC5 | The new runs' `diff`, `deploy` and `smoke` job logs contain each value zero times; the two leaked runs' logs are gone for every attempt | none | live (human-only) | `gh` CLI | the secrets set; the fix merged and run once | `gh run view <run-id> --log --job <job-id> \| grep -cF "$VALUE"` per job and value, with the value read from a local env var, never printed (or the exact method used on 2026-10-28) | — | repo root |
| AC6 | The deploy role allows `ecr:CreateRepository` only on the two agent repository ARNs, and has no `bedrock-agentcore:ListAgentRuntimes` | existing `test_deploy_role_may_call_create_repository_only_on_the_two_agent_repositories` (passes; already written) | unit (CDK synth) | pytest + `aws_cdk.assertions` | none | `uv run pytest tests/test_infra_ci_bootstrap.py -q -k create_repository` | `uv run pytest tests/ -q` | repo root |
| AC6 | The first live agent deploy passes after the grant (verified 2026-10-28) | none | live (human-only, done) | GitHub Actions | the CI access stack redeployed with the grant | recorded in `tasks.md` O1 | — | GitHub |
| AC7 | Job ids and names unchanged (the ruleset check-name cross-check still passes); the diff job keeps its same-repo guard; the smoke job has no `CHAT_API_ID` secret reference | existing `test_ruleset_required_checks_equal_the_pr_workflow_check_names` and `test_diff_*` (unchanged); new `test_smoke_job_does_not_read_the_chat_api_id_secret` | unit (static YAML) | pytest + PyYAML | none | `uv run pytest tests/test_ci_workflows.py -q -k "ruleset or diff or smoke"` | `uv run pytest tests/ -q`; `uv run ruff check .`; `uv run mypy .` | repo root |

## Revision log
- Revision 1 (2026-10-28): first draft.

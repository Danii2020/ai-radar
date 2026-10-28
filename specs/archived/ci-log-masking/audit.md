# Audit: CI Log Masking

Round 1, 2026-10-28. Branch `fix/ci-deploy-ecr-createrepository`, with uncommitted changes on top of
`ff8d56d`. Specs: `intent.md` revision 1 (human-approved 2026-10-28), `execution-plan.md` and
`tasks.md`. Changed files reviewed in full, together with the code that consumes them:
`.github/workflows/backend-pr.yml`, `.github/workflows/backend-deploy.yml`,
`infra/ci_bootstrap/ci_access_stack.py`, `tests/test_ci_workflows.py` and
`tests/test_infra_ci_bootstrap.py`.

Evidence labels: `rerun` = the auditor ran it this round; `reused` = taken from `tasks.md` and
still current; `unavailable` = could not be run here.

Auditor runs (all `rerun` unless marked):
- `uv run pytest tests/ -q` -> **835 passed** (154 s, nothing else running).
  - A first full run gave 834 passed, 1 failed: `tests/test_infra_chat_api.py::test_allowed_origins_context_key_is_ignored`.
    That file passed 3 of 3 times on its own, and the clean full rerun passed.
  - Cause: I ran `uv run mypy .` and `ruff` at the same time. They rewrote `.mypy_cache`/`.ruff_cache`
    in the repo root, which is the Lambda image build context, and `.dockerignore` does not exclude
    those caches. That changed the asset hash between the test's two synths.
  - This predates the change: neither `.dockerignore` nor that test is touched here (the known
    CAAUTH-F3 build-context class). Recorded as a note, not a finding.
- `uv run ruff check .` -> clean. `uv run mypy .` -> clean (122 files). Focused
  `tests/test_ci_workflows.py tests/test_infra_ci_bootstrap.py` -> 93 passed.
- `git diff --stat` on the two workflows: 10 and 6 lines (9 `vars.` lines replaced, plus one changed error message).
- `git diff ff8d56d -- .github/workflows/backend-checks.yml harny-feedback*.yml` -> empty.
- `grep` over `.github/workflows/`:
  - no `vars.` reference, no 12-digit literal, no `set -x`, `printenv` or bare `env`, and no `secrets: inherit`;
  - every `${{ }}` expression is listed below.
- actionlint and shellcheck were **not re-run** (binary download blocked in this session). Reused:
  actionlint 1.7.12 with shellcheck 0.11.0 over all five workflow files, exit 0 (`tasks.md` O8).

### Every `${{ }}` in the backend workflows (rerun)
| File:line | Expression | Carries an id? |
|---|---|---|
| pr:10 | `github.event.pull_request.number` (concurrency group) | no |
| pr:45 | `role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/gha-airadar-diff` | account, secret |
| pr:47 | `github.run_id` | no |
| pr:52, pr:61 | `env: CHAT_API_ID: ${{ secrets.CHAT_API_ID }}` (mask step, diff step) | chat id, secret |
| deploy:32-33 | `steps.plan.outputs.*` | no (target names) |
| deploy:44-45 | `github.token`, `inputs.deploy_all` | no |
| deploy:88 | `…${{ secrets.AWS_ACCOUNT_ID }}:role/gha-airadar-deploy` | account, secret |
| deploy:95 | `EXPECTED_ACCOUNT: ${{ secrets.AWS_ACCOUNT_ID }}` | account, secret |
| deploy:105 | `CHAT_API_ID: ${{ secrets.CHAT_API_ID }}` | chat id, secret |
| deploy:191 | `…${{ secrets.AWS_ACCOUNT_ID }}:role/gha-airadar-smoke` | account, secret |

No step name contains `${{ }}`, and no `run:` text has a `${{ }}` that carries an id.

## Leak analysis (scrutiny item 1)
- **`env:` blocks.** The runner prints a step's `env` before the step runs. Every id now enters
  through `secrets.*`, which the runner registers as a mask before the job starts, so the printed
  block shows `***`. The two leaking places named in the intent (mask-step `env` in `deploy` and
  `diff`) are fixed.
- **`with: role-to-assume`.** The printed input is built from the secret, so it shows
  `arn:aws:iam::***:role/gha-airadar-*`. Secret masking works on substrings, so the derived ARN never
  shows the account id. The same holds for ECR URIs (`<acct>.dkr.ecr…`), stack ARNs and CloudTrail-style
  strings printed later by `cdk`/`agentcore` in the `diff`, `deploy` and `smoke` jobs, because each of
  those jobs references `secrets.AWS_ACCOUNT_ID`. `mask-aws-account-id: true` remains on all three
  credentials steps.
- **Derived chat URL.** `https://<id>.execute-api…` contains the id verbatim, so the secret mask
  covers it in `diff` and `deploy`. The explicit `::add-mask::` lines are redundant but harmless.
- **Expanded `run:` text.** The runner prints the script with `${{ }}` substituted but shell
  variables unexpanded. The scripts hold only `$CHAT_API_ID`/`$EXPECTED_ACCOUNT` shell references, so
  no value appears in the printed script text.
- **PR diff `sed "s/${CHAT_API_ID:-__none__}/***/g"`.** This is a shell expansion inside the step, not
  printed. With the secret masked anyway, the `sed` is now defense in depth. Job summaries mask
  secrets (GitHub docs).
- **Account guard.** `actual` is captured, never echoed. The failure message is static.
- **Error messages.** These are static strings ("the CHAT_API_ID secret is not set; stopping before any
  deploy", "caller account does not match…").
- **Smoke job.** It references `secrets.AWS_ACCOUNT_ID` (role ARN), so the account id is masked
  there. It does not reference `secrets.CHAT_API_ID`, so the runner registers no chat-id mask for that
  job. It still relies on its own stack-read `::add-mask::` (fail-open, CICD-F10, out of scope) and on
  `scripts/ci/smoke.py` masking before any print. In my round-2 review of `backend-cicd-pipeline` I
  found no print path that precedes those masks, and the intent records that smoke did not leak. AC7
  requires this behaviour to stay unchanged.
- **Jobs without secrets** (`checks`, `plan`, `diff-skipped`) print no id. `plan` prints target names.
  `checks` does not print templates (`cdk synth --quiet`). Literals already in git history are out of
  scope.

## Fail-closed and forks (scrutiny item 2)
- **Fork PR.** The `diff` job is gated by `head.repo.full_name == github.repository`, so it is skipped
  before any secret is needed. `diff-skipped` prints static text, and `checks` uses no secret.
  Nothing breaks and nothing prints.
- **Same-repo PR with the secrets unset.** The role ARN becomes `arn:aws:iam:::role/gha-airadar-diff`.
  The credentials step fails, there is no AWS access and no id to leak. The PR mask step is tolerant
  of an empty value, as the plan requires.
- **Deploy with `CHAT_API_ID` unset.** The job stops at the mask step (`exit 1`) before the
  pre-deploy checks and every `cdk deploy`.
- **Deploy with `AWS_ACCOUNT_ID` unset.** The ARN is invalid, the credentials step fails, and the
  guard would also fail on an empty value. The guard script was executed against a shimmed `aws` by
  `test_account_guard_compares_with_the_secret_and_fails_on_empty` (equal: 0; differ: non-zero;
  empty: non-zero) (rerun).
- **Dependabot.** Not adopted. Its PRs would read Dependabot secrets and fail closed in `diff`
  (intent open item). There is no leak.

## AC results
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | No `vars.*` left in any workflow. Every id-carrying expression is `secrets.CHAT_API_ID`/`secrets.AWS_ACCOUNT_ID` (table above). Tests `test_no_workflow_references_the_retired_repository_variables` and `test_ids_reach_steps_only_through_secrets` (+ 4 detector fixtures) pass (rerun). |
| AC2 | PASS | The three ARNs are `arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/gha-airadar-{diff,deploy,smoke}`, equal to `DIFF_ROLE`/`DEPLOY_ROLE`/`SMOKE_ROLE` in `ci_access_stack.py`. The test imports the constants. The three differ. `mask-aws-account-id: true` is on all three. The OIDC trust is untouched (`SUB_PR`, `SUB_MAIN` unchanged), and the sub is a property of the workflow trigger, not of the role ARN (rerun). |
| AC3 | PASS | The deploy mask stops on empty, precedes every `cdk deploy` and contains no stack read or suppression. The guard compares with the secret and fails on empty or a mismatch (executed test). An empty account id breaks the ARN (rerun). |
| AC4 | PASS (F2) | Secret names used: `AWS_ACCOUNT_ID`, `CHAT_API_ID`. Allow-list `{GITHUB_TOKEN, CHAT_API_ID, AWS_ACCOUNT_ID}`. No `secrets: inherit`. `backend-checks.yml` has no secret (rerun). The test misses the bracket and whole-context forms (F2). |
| AC5 | N/A (live, human-only) | O4 and O6 are not run yet. |
| AC6 | PASS | `ecr:CreateRepository` was added to the existing ECR statement, whose resources are exactly `repository/bedrock-agentcore-ai_radar_curation` and `repository/bedrock-agentcore-ai_radar_chat`. No other action was added. `ListAgentRuntimes` appears nowhere in the stack (grep). The test passes (rerun). Live pass: reused (O1, coordinator-reported). The pyright-only ignore is a comment and changes no behaviour or template. |
| AC7 | PASS | No job, check or step-structure change. Triggers, concurrency (`backend-deploy`/false, PR per-number/true), permissions and the same-repo guard are unchanged (diff is `vars.` lines plus one message only). The ruleset check-name cross-check passes. The smoke job has no `CHAT_API_ID` secret (test) and keeps deriving the id from AWS. Deploy and smoke still run on `main` only (rerun). |

## Binding-constraint compliance
| Constraint | Status | Evidence |
|---|---|---|
| Exactly two secrets, no other new secret | PASS | Only `CHAT_API_ID` and `AWS_ACCOUNT_ID` are referenced. |
| ARNs built from the secret account and the stack names; names literal | PASS | See AC2. |
| `mask-aws-account-id: true` everywhere | PASS | 3 of 3 steps. |
| Deploy mask fails on empty and precedes every `cdk deploy`; PR mask tolerant | PASS | Workflow text and `-k mask_deploy` tests. |
| Account guard logic unchanged, source changed | PASS | Only the `env` line differs. |
| No job or check name change | PASS | Diff plus the cross-check test. |
| No secrets to the reusable workflow; no `secrets: inherit` | PASS | `checks` jobs have no `secrets:` key, and `backend-checks.yml` is unchanged. |
| Values never committed or echoed | PASS | No literal in the workflows or tests (fakes `"1"*12`/`"2"*12` only). |
| Dependencies | PASS | None added (`pyproject.toml`/`uv.lock` untouched). |

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `tests/test_ci_workflows.py::test_no_workflow_references_the_retired_repository_variables`, `::test_ids_reach_steps_only_through_secrets`, `::test_ids_detector_*` | PASS |
| AC2 | `::test_role_arns_are_built_from_the_secret_account_and_the_stack_role_names`, `::test_diff_job_assumes_the_diff_role_built_from_the_secret_account_and_is_the_only_job_with_an_id_token`, `::test_deploy_trigger_deploy_job_authenticates_through_oidc_with_the_built_deploy_role`, `::test_smoke_job_uses_its_own_oidc_role_distinct_from_the_deploy_role` | PASS |
| AC3 | `::test_mask_deploy_*` (5 + the stop-on-empty case), `::test_account_guard_compares_with_the_secret_and_fails_on_empty` | PASS |
| AC4 | `::test_workflows_reference_only_allow_listed_secrets_and_never_inherit`, `::test_the_reusable_checks_workflow_references_no_secret` | PASS (weak, F2) |
| AC5 | none (live) | N/A |
| AC6 | `tests/test_infra_ci_bootstrap.py::test_deploy_role_may_call_create_repository_only_on_the_two_agent_repositories` | PASS (does not assert the absence of `ListAgentRuntimes`; the auditor's grep confirms it, F3) |
| AC7 | `::test_ruleset_required_checks_equal_the_pr_workflow_check_names`, `::test_diff_*`, `::test_smoke_job_does_not_read_the_chat_api_id_secret` | PASS |

Red evidence: `tasks.md` O2 records 8 tests red for the right reason (`vars.*` sources) and the
satisfiability check. The allow-list, checks-has-no-secret, smoke-has-no-chat-id and detector tests
are green by design.

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (static YAML) | `tests/test_ci_workflows.py` | AC1, AC2, AC3, AC4, AC7 | yes (no new setup) | rerun (green) | PASS | F2 |
| unit (CDK synth) | `tests/test_infra_ci_bootstrap.py` | AC6 | yes | rerun (green) | PASS | F3 |
| live (human-only) | none | AC5, AC6 (done) | n/a | not run: human-only (O4, O6); AC6 live reused (O1) | N/A | F4 |

No test sits at an unnamed tier, and no setup was added.

## Human-only steps (scrutiny item 7)
The order in `tasks.md` is correct:
1. O3: secrets before the PR opens. The PR's own `diff` runs the PR's workflow and needs them.
2. O4: grep after the PR diff run and the first deploy run.
3. O5: delete the variables only after the merge and a successful run. `main`'s old workflow reads them until then.
4. O6: delete the leaked runs' logs after the fix has run once.

The grep method is sound in principle. The stored logs are already masked by the runner, so `grep -cF`
on downloaded logs tests exactly what the public sees, and `-c` prints a count, never the value.
Two cautions for the human:
- Read the value without echo or shell history (`read -rs VALUE`), and don't put it on a command line.
- Don't re-run the two leaked runs. A re-run uses their original commit's workflow and would leak again.
  (O5 deleting the variables first would make such a re-run fail instead.)

## Findings
| Id | Severity | Cites | Finding | Closure condition | Status |
|---|---|---|---|---|---|
| F1 | LOW | Outcome completion | `tasks.md` is stale. Status still reads "Awaiting intent approval", and Working state (Phase "spec drafted, awaiting human approval"; next step "the test-writer writes the O2 red tests") and Checkpoint predate the implementation. O2 and O8 are done. The baseline "Pre-existing failures: to be recorded" is never filled in (O8 does give 827 passed + 8 intended red). O3–O6 are correctly unticked and human-only; O7 (docs) and O9 (audit) are correctly open. | Refresh Status, Baseline, Working state and Checkpoint. | Open |
| F2 | LOW | AC4 (test strength) | The allow-list test matches only the `secrets.NAME` form. `${{ secrets['SOME_TOKEN'] }}` or `${{ toJSON(secrets) }}` would pass it. `test_the_reusable_checks_workflow_references_no_secret` uses the substring `secrets.`, so `secrets[` would slip past it too. The workflows today use only the dotted form, so this is not a defect of the change. | Also flag `secrets[` and any `secrets` used outside `secrets.<allowed>` (for example `toJSON(secrets)`), with a fixture. | Open |
| F3 | LOW | AC6 | The AC6 test pins the `CreateRepository` scope but does not assert the deploy role lacks `bedrock-agentcore:ListAgentRuntimes`, which the AC states. The auditor's grep shows it is absent. | Add the negative assertion (or record why the existing deploy-role tests already cover it). | Open |
| F4 | LOW | AC5 | The live tier is not run (human-only, O4/O6), and so is the open question about deleting logs for every attempt. | O4 grep counts 0 per job and value. O6 deletion confirmed for every attempt. | Open (expected) |

Notes (not findings):
- The full-suite flake described above predates this change and was induced by my concurrent `mypy`/`ruff` writing caches into the Lambda build context.
- The README "Backend CI/CD" bootstrap step 2 still tells the human to set the five variables (line ~1528). It must be rewritten in the documentation step (O7) before anyone follows the runbook again.

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-28 | APPROVED WITH RESERVATIONS | AC1–AC4, AC6, AC7 pass on the workflow text, not only on the tests. No remaining pre-mask print path for either id in `diff` or `deploy`. Fail-closed on missing secrets. Fork PRs skip safely. ECR grant scoped to the two repositories. F1–F4 are LOW. 835 passed; ruff and mypy clean. |

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: Both identifiers now enter the backend workflows only as repository secrets, so the
runner masks them from the first log line in the `diff`, `deploy` and `smoke` jobs, including `env`
blocks, the `role-to-assume` input and derived ARNs and URLs. The role ARNs match the stack's role
names. Every missing-secret path fails closed without printing. Nothing else changed behaviour. The
reservations are LOW and the live verification is still to run.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F1: refresh `tasks.md` (Status, Baseline, Working state, Checkpoint).

**Recommendations** (nice to have):
- F2: harden the allow-list test against `secrets[...]` and `toJSON(secrets)`.
- F3: assert the absence of `ListAgentRuntimes` in the AC6 test.

**Human-only steps remaining:** O3 (set both secrets via `gh secret set`, before opening the PR),
O4 (zero-count grep of the new `diff`, `deploy` and `smoke` logs), O5 (delete the five variables after
the merge and a clean run), O6 (delete the two leaked runs' logs for every attempt and confirm).

**Documentation step (after this gate):** ADR 0048 (amends ADR 0040), README "Backend CI/CD"
bootstrap step 2 (two secrets via `gh secret set`, role ARNs no longer variables, the stale-id note
now about the secret), `specs/current/ci-cd.md` (CICD-11 masks from `secrets.CHAT_API_ID`, CICD-15 new
allow-list, the no-`vars.*` and role-name invariants, and a new reservation for this live finding), and
the `CLAUDE.md` pointer if it mentions the variables.

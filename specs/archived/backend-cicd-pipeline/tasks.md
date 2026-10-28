# Tasks: Backend CI/CD Pipeline

## Status
Repaired, awaiting re-audit (round 1 REJECTED 2026-10-27; spec revision 3 fixes O14-O20 done by the executor 2026-10-28; O12 human-only, O13 re-audit open)

## Baseline
- Base commit: a49c308 (Merge pull request #10 from Danii2020/feat/web-chat-ui)
- Branch: main (the implementer branches first, for example `feat/backend-cicd-pipeline`)
- Interpreter: Python 3.12.11 (uv 0.7.17)
- Cwd: /Users/danielerazo/python/project-agentcore-app
- Commands: `uv run pytest tests/ -q`; `uv run ruff check`; `uv run mypy .`; `actionlint` (once installed)
- Pre-existing failures: none. `uv run pytest tests/ -q` at a49c308 on 2026-10-27 gave 559 passed,
  202 warnings, in 397 s (the full suite takes about 6.5 minutes locally, mostly CDK synth tests).
  ruff and mypy were clean at the round 1 rerun (121 files). Untracked `specs/archived/chat-agent-runtime/.sdd/`
  exists in the working tree and is unrelated to this feature.

## Outcomes
- [x] **O1** (AC6, AC15): Pinned deploy context file (four keys, including
  `feed_api_allowed_origins` = `http://localhost:3000` until the real Vercel URL exists), the `cdk`
  wrapper that applies it, the origin validation, and the schedule guard over the synthesized
  `AiRadarSchedule` template.
  - Tests: `tests/test_ci_deploy_context.py` (AC6 pinned keys and wrapper, AC15 origin validation and CORS equals the file), `tests/test_ci_schedule_guard.py` (AC6 guard); shared helper `tests/ci_synth_helpers.py`
  - Red: 2026-10-27, all red for the right reason: `ModuleNotFoundError: No module named 'scripts.ci'` (22 tests) and `FileNotFoundError: .../scripts/ci/deploy_context.json` (5 + 5 synth-fixture errors in the guard tests)
  - Green: 2026-10-27 (executor): `uv run pytest tests/test_ci_deploy_context.py tests/test_ci_schedule_guard.py -q` green; wrapper also ran a real `cdk synth` offline and the guard passed on it
- [x] **O2** (AC4, AC5): Deploy planner: base from the last successful deploy run, changed paths,
  committed path-to-target mapping, fail-safe "all", pinned dependency order.
  - Tests: `tests/test_ci_deploy_plan.py` (AC4 base cases, AC5 mapping and order)
  - Red: 2026-10-27: `ModuleNotFoundError: No module named 'scripts.ci'` on all 44 tests
  - Green: 2026-10-27 (executor): `uv run pytest tests/test_ci_deploy_plan.py -q` green (44)
- [x] **O3** (AC6): CI AgentCore config template and renderer (checkout `source_path`, execution
  roles from stack outputs, pinned `agent_id`/`agent_arn`, auto-create off, fails on missing values).
  - Tests: `tests/test_ci_agentcore_config.py` (AC6 rendered config)
  - Red: 2026-10-27: `ModuleNotFoundError: No module named 'scripts.ci'` on all 12 tests
  - Green: 2026-10-27 (audit rerun) and 2026-10-28 (executor full run, 823 passed), after the conductor-routed fix to the red test (`["out"]` -> `["cwd", "out"]`,
    judged legitimate and not weakened in `audit.md` round 1): the auditor's full-suite rerun,
    783 passed, includes all 12 tests (reused from `audit.md`). The deployability of the rendered
    config with `--local-build` is not covered here; see O14.
- [x] **O4** (AC7, AC10): Smoke runner (four probes after every deploying run, masking, one bounded
  retry on the signed probe) and the opt-in exit-code option on `run_chat_api_smoke.py`.
  - Tests: `tests/test_ci_smoke.py` (AC7 four probes, retry, AC10 no leak), `tests/test_chat_api_smoke.py` (extended, AC7 opt-in `--expect-status` / `--expect-keys`)
  - Red: 2026-10-27: `test_ci_smoke.py` 24 tests `ModuleNotFoundError: No module named 'scripts.ci'`; `test_chat_api_smoke.py` 6 new tests fail with `SystemExit: 2` (`unrecognized arguments: --expect-status`), the default-mode test and the 6 existing tests stay green (7 passed)
  - Green: 2026-10-27 (executor): `uv run pytest tests/test_ci_smoke.py tests/test_chat_api_smoke.py -q` green; default `main()` still returns 0
- [x] **O5** (AC2, AC3, AC8, AC9): CI access CDK app, separate from `infra/app.py`, with
  `CliCredentialsStackSynthesizer`: GitHub OIDC provider and the diff, deploy and smoke roles with
  exact trust subjects and names outside the `AiRadar*`/`ai-radar*` patterns.
  - Tests: `tests/test_infra_ci_bootstrap.py` (AC2 diff role, AC3 deploy role, AC8 smoke role, AC9 shape)
  - Red: 2026-10-27: `ModuleNotFoundError: No module named 'ci_bootstrap'` on all 18 tests
  - Green: 2026-10-27 (executor): `uv run pytest tests/test_infra_ci_bootstrap.py -q` green (18)
- [x] **O6** (AC13): Scoped CloudFormation execution managed policy in the CI access app (name
  outside the `AiRadar*` pattern, explicit denies), plus the resource-type coverage test over the
  seven synthesized stacks and the shape test.
  - Tests: `tests/test_infra_ci_cfn_exec_policy.py` (AC13 coverage and shape)
  - Red: 2026-10-27: `ModuleNotFoundError: No module named 'ci_bootstrap'` on all 59 tests
  - Green: 2026-10-27 (executor): `uv run pytest tests/test_infra_ci_cfn_exec_policy.py -q` green (59); added `tests/test_infra_ci_policy_size.py` (policy under the 6,144-char IAM limit)
- [x] **O7** (AC14): Repository-protection script: dry run by default, `--apply` to write,
  read-then-diff idempotency; ruleset on `main`, secret scanning and push protection, read-only
  default workflow token, approval for outside contributors' workflow runs. Each endpoint confirmed
  against GitHub's REST docs; any setting without an API listed as a manual runbook step.
  - Tests: `tests/test_ci_repo_protection.py` (AC14 dry run, apply, idempotency, payloads; `gh` runner faked)
  - Red: 2026-10-27: `ModuleNotFoundError: No module named 'scripts.ci'` on all 12 tests
  - Green: 2026-10-27 (executor): `uv run pytest tests/test_ci_repo_protection.py -q` green (12)
- [x] **O8** (AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC10, AC14, AC16): Workflows: reusable checks,
  PR (checks plus same-repo diff to the job summary), deploy (checks, plan, ordered deploy, smoke)
  with fixed no-cancel concurrency, SHA-pinned actions, uv cache, `timeout-minutes` on every job,
  least-privilege `permissions`, mask steps; `.github/CODEOWNERS`. `pyyaml` declared in the `dev`
  group if the tests parse YAML. The required check names match the protection script's constant.
  - Tests: `tests/test_ci_workflows.py` (AC1-AC10, AC14 check-name cross-check, AC16 `-k hardening`); `actionlint` clean (lint tier: not run, actionlint is not installed)
  - Red: 2026-10-27: 47 tests fail with `AssertionError: .github/workflows/backend-*.yml does not exist` / `.github/CODEOWNERS does not exist` (or `ModuleNotFoundError: scripts.ci` for the check-name cross-check)
  - Green: 2026-10-27 (executor): `uv run pytest tests/test_ci_workflows.py -q` green (49); actionlint 1.7.7 (darwin_arm64, checksum-verified, in the scratchpad, not a project dependency) clean on the three backend workflows (shellcheck not installed, so shell checks within it did not run)
- [x] **O9** Migration (AC12): no edit to `harny-feedback.yml` or `harny-feedback-apps-web.yml`;
  existing `tests/test_chat_api_smoke.py` and `tests/test_infra*.py` pass unchanged; synthesized
  templates of the seven stacks compared with the base commit and identical (the pinned origins
  equal the current default).
  - Evidence 2026-10-27 (auditor rerun, `audit.md`): seven templates identical with the pinned context and with the earlier runbook context. 2026-10-28 (executor): `git status` shows no change under `infra/lib`, `infra/stacks`, `infra/app.py`, `Dockerfile*`, `.dockerignore`, `harny-feedback*.yml`; only `infra/ci_bootstrap/` changed.
- [x] **O10** Docs (AC11, AC15): README "Backend CI/CD" runbook: the CI access stack deploy, repository
  variables for the role ARNs, the CDK re-bootstrap with the scoped policy (verification and rollback
  to `AdministratorAccess`, and the note that it governs human deploys too), the protection script
  (dry run, apply, read-back), first run, what deploys in which order, reading the PR diff, smoke cost,
  rollback by revert or by hand, the context file and adding the Vercel origin by PR, and the
  public-repository risk register (execution plan § Public repository risks). Notes in the existing
  runbooks that CI now deploys on merge; the README "Still open" CORS item and the `apps/web` Vercel
  runbook point at the context file.
  - Re-reviewed 2026-10-28 after O18: feed-api CORS command repaired, CI-access command in `uv run cdk` form, two-ARN re-bootstrap and rollback text. The re-audit should re-read it.
- [x] **O11** Broader suite vs baseline: `uv run pytest tests/ -q`, `uv run ruff check`,
  `uv run mypy .`, `actionlint` — result vs baseline.
  - Round 1 (auditor rerun, `audit.md`): 783 passed, ruff and mypy clean. Superseded by O20 (2026-10-28): 823 passed, ruff and mypy clean, actionlint 1.7.12 with shellcheck 0.11.0 clean on all five workflow files.
- [x] **O14** (AC5, AC6; audit F1): The deploy job runs `mkdir -p` and copies the repo-root
  `Dockerfile` to `.bedrock_agentcore/ai_radar_curation/Dockerfile` and
  `.bedrock_agentcore/ai_radar_chat/Dockerfile` (beside the rendered config) before each
  `agentcore deploy`; the test computes the expected path with the toolkit's own
  `get_agentcore_directory` and fails when the step is absent, misordered, or misses an agent.
  - Tests: `tests/test_ci_workflows.py` (`-k dockerfile`; the test computes each agent's directory with the toolkit's `get_agentcore_directory` on a rendered config, runs the deploy job's steps before each `agentcore deploy` in a scratch workspace with shimmed tools, and checks the root Dockerfile landed there; fixture workflows prove the detector flags a removed step, a missing agent, a late step and a wrong source)
  - Red: 2026-10-28: `test_dockerfile_the_deploy_job_places_the_root_dockerfile_where_the_toolkit_reads_it` fails: `ai_radar_curation: .bedrock_agentcore/ai_radar_curation/Dockerfile does not exist before its deploy step` (and the same for `ai_radar_chat`); the 6 detector tests pass
  - Green: 2026-10-28 (executor): `.github/workflows/backend-deploy.yml` gets a step "Place the root Dockerfile where agentcore reads it" (same `if` as the config render step) that runs `mkdir -p .bedrock_agentcore/<agent>` and `cp Dockerfile` for both agents, before the first `agentcore deploy`. `uv run pytest tests/test_ci_workflows.py -k dockerfile -q`: 7 passed
- [x] **O15** (AC13; audit F2): Execution policy split into at most two customer-managed policies
  (both named `cdk-exec-airadar*`, outside `AiRadar*`), each under 6,144 characters; committed
  handler-permission snapshot from the public CloudFormation schema zip and an omission list with
  reasons; the audit's missing actions added; `iam:CreateServiceLinkedRole` not added; coverage,
  shape and size tests updated from "exactly one policy" to the union of one or two. Human
  decisions (2026-10-28): `secretsmanager:GetSecretValue` only on `secret:ai-radar/tavily-api-key-*`;
  DynamoDB item actions only on `table/ai-radar-cards` and its `feed-by-score` index; the
  `dynamodb:DeleteTable` deny kept, with the GlobalTable replica-removal conflict in the omission
  list (table `RETAIN`, no replicas, future replica removal is a manual step). Tests cover the
  scoped-secret and deny-vs-omission cases. The README re-bootstrap section and risk register
  record the same (with O18).
  - Tests: `tests/test_infra_ci_cfn_exec_policy.py` (`-k coverage`, `-k shape`; union of one or two policies), `tests/test_infra_ci_policy_size.py` (each policy); committed fixtures `tests/fixtures/cfn/handler_permissions.json` (handler snapshot extracted 2026-10-28 from the public CloudFormation schema zip) and `tests/fixtures/cfn/handler_omissions.json` (omission list with reasons)
  - Red: 2026-10-28: 4 fail. `test_coverage_every_handler_permission_..._allowed_or_omitted` names 9 types with unallowed handler permissions (e.g. `AWS::Budgets::Budget`: `billing:GetBillingViewData`, `budgets:ListTagsForResource`, `budgets:TagResource`); `test_coverage_the_actions_the_audit_found_missing_are_allowed` lists 22 missing audit actions (first: `lambda:GetFunctionCodeSigningConfig`); `test_coverage_the_omitted_table_deletes_are_not_also_allowed` and `test_coverage_flags_the_delete_table_permission_when_its_omission_entry_is_removed` fail because the policy still allows `dynamodb:DeleteTable`. The Tavily-secret, item-action, size and two-policy deny tests pass today (the current single policy already satisfies them) and guard the split
  - Green: 2026-10-28 (executor): `infra/ci_bootstrap/ci_access_stack.py` now defines two policies, `cdk-exec-airadar` (data and compute services, 4,480 chars without whitespace) and `cdk-exec-airadar-2` (IAM, scheduler, budgets and every deny, 3,264 chars). Missing handler actions added; `GetSecretValue` only on `secret:ai-radar/tavily-api-key-*`; item actions only on `table/ai-radar-cards` and `index/feed-by-score`; `DeleteTable`/`DeleteTableReplica` not allowed and the `ai-radar-cards` deny kept; no `iam:CreateServiceLinkedRole`. Outputs `ExecutionPolicyArn1` and `ExecutionPolicyArn2`. `uv run pytest tests/test_infra_ci_cfn_exec_policy.py tests/test_infra_ci_policy_size.py tests/test_infra_ci_bootstrap.py -q`: 105 passed. Judgment calls to review: `logs:PutResourcePolicy`/`DeleteResourcePolicy` and `cloudwatch:PutMetricData`, `secretsmanager:GetRandomPassword`, `billing:GetBillingViewData` are on `*` (no resource-level support); `iam:AttachUserPolicy`/`DetachUserPolicy` on the caller user are conditioned to `policy/AiRadar*`
- [x] **O16** (AC13; audit F3): Resource-coverage test: every physical name in the seven templates
  matches the allow statements' `Resource` patterns, with a failing out-of-pattern fixture.
  - Tests: `tests/test_infra_ci_cfn_exec_policy.py` (`-k resource_coverage`; the fixture Lambda named `other-fn` and a generated-name Lambda are flagged, API Gateway v2 is exempt)
  - Red: 2026-10-28: no red by design: all 7 per-stack tests and the 3 detector tests pass today (the auditor found every current physical name matches); they fail when a name leaves the AiRadar*/ai-radar* patterns
  - Green: 2026-10-28 (executor): unchanged policy-side tests still pass with the new policies (`-k resource_coverage` inside the 105 above)
- [x] **O17** (AC10; audit F5): The deploy job masks from `vars.CHAT_API_ID` and its chat-URL read
  fails closed (no `|| true`, no error suppression).
  - Tests: `tests/test_ci_workflows.py` (`-k mask_deploy`)
  - Red: 2026-10-28: `test_mask_deploy_job_masks_from_the_repository_variable_and_fails_closed` fails with 4 problems: `no mask step uses vars.CHAT_API_ID`, `mask step swallows a failure: ... 2>/dev/null || true`, and the ordering problem; the 4 detector tests pass
  - Green: 2026-10-28 (executor): the deploy job's mask step reads `vars.CHAT_API_ID` into `CHAT_API_ID`, stops the job when it is empty, and masks the id and the derived URL before any `cdk deploy`; the stack-output read (with `|| true` and `2>/dev/null`) is removed from the deploy job. `uv run pytest tests/test_ci_workflows.py -k mask_deploy -q`: 5 passed. Not changed: the smoke job's own mask step still reads the stack output with `|| true` (outside the F5 test and finding; flagged for the re-audit)
- [x] **O18** (AC11, AC12; audit F4, F9): README repair: the feed-api CORS `cdk deploy` command no
  longer has comment lines inside its backslash continuation; the CI-access deploy command uses
  the repo's `uv run cdk …` form; the re-bootstrap and rollback text cover two policy ARNs.
  - Tests: `tests/test_readme_runbooks.py` (F4 pinned; F9 and the two-ARN text are docs review)
  - Red: 2026-10-28: `test_no_readme_shell_block_has_a_comment_line_inside_a_continued_command` fails: `README.md line 873: # (since backend-cicd-pipeline: put the origin in scripts/ci/deploy_context.json by PR`; the 2 detector tests pass
  - Green: 2026-10-28 (executor): README feed-api CORS command has no comment lines in its continuation (note moved above the block); CI-access deploy is `uv sync --group infra` then `uv run cdk deploy --app "python infra/ci_bootstrap/app.py" CiAccess -c chat_api_id=<chat-api-id>`; re-bootstrap uses `--cloudformation-execution-policies "<ExecutionPolicyArn1>,<ExecutionPolicyArn2>"` and the rollback says AdministratorAccess replaces both. `uv run pytest tests/test_readme_runbooks.py -q` green
- [x] **O19** (AC1; audit F7): actionlint 1.7.12 with shellcheck over all five files in
  `.github/workflows/`; result recorded here.
  - Result 2026-10-28 (executor): actionlint 1.7.12 (darwin_arm64, sha256 checked against the release checksums file) with shellcheck 0.11.0 (darwin.aarch64, sha256 checked against the GitHub release digest), both in the scratchpad, no project dependency. `actionlint .github/workflows/*.yml` over all five files (`backend-checks`, `backend-deploy`, `backend-pr`, `harny-feedback`, `harny-feedback-apps-web`): exit 0, no findings. shellcheck was on PATH, so the `run:` scripts were checked.
- [x] **O20** Broader suite after the repairs: `uv run pytest tests/ -q`, `uv run ruff check .`,
  `uv run mypy .` — result vs the round 1 rerun (783 passed).
  - Result 2026-10-28 (executor): `uv run pytest tests/ -q` 823 passed, 202 warnings, 150 s (round 1: 783; the 7 intended-red tests are green); `uv run ruff check .` clean; `uv run mypy .` clean (122 files).
- [ ] **O12** Live verification (human-only; no agent runs these), in this order:
  (a) deploy the CI access app with admin credentials and the chat API id as context; record the
  three role ARNs as repository variables;
  (b) re-bootstrap CDK with `--cloudformation-execution-policies "<policy-arn-1>,<policy-arn-2>"`
  (the two policies from the stack outputs `ExecutionPolicyArn1` and `ExecutionPolicyArn2`); `cdk synth` and
  `cdk diff` of all seven stacks with the pinned context show no differences; keep the rollback
  command ready;
  (c) run the protection script in dry run, then `--apply`; read the ruleset and
  `security_and_analysis` back; confirm a direct push to `main` is rejected;
  (d) a same-repo PR shows the seven-stack diff and the required checks; a fork PR (or a simulated
  one) shows the skip line and needs workflow approval;
  (e) the first merge deploys under the scoped execution policy; the smoke passes; both agents keep
  their runtime ids; `AiRadarSchedule` is `DISABLED`; the budget limit is 500; the feed CORS origins
  are unchanged; the chat URL is masked in the public log;
  (f) the deploy role gets 403 and the smoke role 200 on a signed `POST /v1/chat`;
  (g) a docs-only merge reports nothing to deploy and runs no smoke;
  (h) confirm the deploy-role allow-list from CloudTrail and any `AccessDenied` (human answer to Q5),
  and the execution-policy gaps from CloudFormation events; fix both by PR and record them in the
  README;
  (i) when the Vercel project exists: add its origin to the context file by PR and check the
  preflight (open item).
- [ ] **O13** Independent audit: round 1 REJECTED (2026-10-27, `audit.md`; F1 CRITICAL, F2 HIGH, F3–F6 MEDIUM, F7–F9 LOW). Re-audit (round 2) after O14–O20.

## Working state
- Updated: 2026-10-28 (executor, repair pass)
- Outcome: O1–O11 and O14–O20 done; O12 human-only and open; O13 re-audit open
- Phase: awaiting re-audit (round 2)
- In progress: —
- Last command: `uv run pytest tests/ -q`: 823 passed (ruff and mypy clean)
- Next step: auditor round 2 (O13); the human runs O12 in order.

## Finding responses
| Finding | Response | Evidence |
|---|---|---|
| F1 (audit round 1) | Fixed: O14. Fix path "option A" approved by the human 2026-10-28. | O14 Green; `-k dockerfile` 7 passed |
| F2 | Fixed: O15 (two policies, 4,480 and 3,264 chars). | O15 Green; 105 passed |
| F3 | Fixed: the resource-coverage tests pass against the two-policy union (`-k resource_coverage`). | O16 Green |
| F4 | Fixed: O18, comment lines moved out of the continued command. | `tests/test_readme_runbooks.py` green |
| F5 | Fixed in the deploy job: O17. The smoke job's mask step is unchanged and still swallows a read error (flagged). | `-k mask_deploy` 5 passed |
| F6 | Status, O3, O9, O10, O11, the outcome ticks, Working state and Checkpoint refreshed; O12 stays human-only and O13 open. | this file |
| F7 | Done: O19, all five files, with shellcheck. | actionlint exit 0 |
| F8 | O12 stays human-only and unticked. | — |
| F9 | Fixed: O18, `uv run cdk deploy` form. | README |
| Red test bug (O3) | `test_render_writes_only_inside_the_output_directory` creates `tmp_path/'cwd'` itself and then asserts `tmp_path` holds only `['out']`, so it cannot pass for any implementation. Not edited; reported to the architect. The renderer writes only `<output_dir>/.bedrock_agentcore.yaml` and touches nothing in cwd (the `cwd` half of the test passes). | `uv run pytest tests/test_ci_agentcore_config.py -q`: 11 passed, 1 failed (that test) |

## Checkpoint
Repair pass done 2026-10-28: O14–O20 green. Resume at the round 2 audit (O13); O12 is the human's.

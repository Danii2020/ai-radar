# Audit: Backend CI/CD Pipeline

Current round: **2** (2026-10-28), against spec revision 3. The human approved revision 3 on
2026-10-28, including the four AC13 decisions. Round 1 (2026-10-27, REJECTED) is kept below under
"Round 1 record" for history.

Branch `feat/backend-cicd-pipeline`. The working tree is uncommitted on top of `f040d41`; the infra
comparison base is `a49c308`. This round re-read every file the repair pass touched:
- `.github/workflows/backend-deploy.yml`
- `infra/ci_bootstrap/ci_access_stack.py`
- `tests/fixtures/cfn/handler_permissions.json` and `tests/fixtures/cfn/handler_omissions.json`
- `tests/test_infra_ci_cfn_exec_policy.py`, `tests/test_infra_ci_policy_size.py`,
  `tests/test_ci_workflows.py` (`-k dockerfile`, `-k mask_deploy`) and the new `tests/test_readme_runbooks.py`
- the `README.md` "Backend CI/CD" section and the feed-api CORS runbook
- `tasks.md`

Evidence labels: `rerun` means the auditor ran it this round. `reused` means it is taken from
`tasks.md` and still current. `unavailable` means it could not be run here.

Auditor runs this round (all `rerun` unless marked):
- `uv run pytest tests/ -q`: 823 passed, 202 warnings, 154 s.
- `uv run ruff check .`: clean. `uv run mypy .`: clean (122 files). The caller asked for both; the
  skill would normally verify them through `harny-feedback` instead.
- `git diff --stat a49c308 -- infra/lib infra/stacks infra/app.py infra/cdk.json Dockerfile*
  .dockerignore .github/workflows/harny-feedback*.yml`: empty.
- No `626259825216`/`536697225154` literal and no 12-digit id in `scripts/`, `infra/ci_bootstrap/`,
  `.github/`, `tests/fixtures/` or the new tests.
- **F1 reproduction, inverted.** I rendered the CI config into a scratch workspace that holds the
  root `Dockerfile` and ran the deploy job's copy loop verbatim. Then I resolved each agent's path
  with the toolkit's own `get_agentcore_directory(cwd, agent, source_path)` from the rendered config,
  loaded with `load_config`. Both `.bedrock_agentcore/ai_radar_{curation,chat}/Dockerfile` exist and
  are byte-identical to the root `Dockerfile`, and `source_path` is the workspace.
- **Handler snapshot fidelity.** `tests/fixtures/cfn/handler_permissions.json` (19 types) was compared
  set-for-set with the round-1 download of the public `CloudformationSchema.zip`: create, read, update
  and delete match for every type, with 0 mismatches.
- **Coverage recomputed independently.** Every handler permission of every type in the seven synthesized
  templates is either allowed by the union of the two policies or matched by an omission. Every
  omission is used, and nothing is uncovered.
- **Policy sizes** with intrinsics resolved and whitespace removed: `cdk-exec-airadar` 4,480,
  `cdk-exec-airadar-2` 3,264. Both are under 6,144.
- **Template properties** that would need an omitted action: none. No KMS key, VPC config, replica
  region beyond the home region, permissions boundary, group, login profile, log-group resource
  policy or layer appears in any of the seven templates.
- **README.** Every fenced block was scanned, not only `bash`/`sh` (the languages used are `bash`,
  `sql` and untagged). No comment line follows a backslash continuation.
- **Not re-run: actionlint and shellcheck.** Downloading the binaries was blocked by the session's
  permission classifier in round 1, and I did not retry. The executor's run is `reused`: actionlint
  1.7.12 and shellcheck 0.11.0, checksum-verified, over all five workflow files, exit 0
  (`tasks.md` O19).

## AC results (round 2)
| AC | Status | Evidence |
|---|---|---|
| AC1 | PASS | Unchanged since round 1 (rerun suite green). actionlint over all five workflows with shellcheck is reused (O19). Live PR check: human-only. |
| AC2 | PASS | Unchanged (rerun). |
| AC3 | PASS | Unchanged (rerun). |
| AC4 | PASS | Unchanged (rerun). |
| AC5 | PASS | Planner unchanged. The agent step can now complete (F1 closed, rerun reproduction). |
| AC6 | PASS | Step "Place the root Dockerfile where agentcore reads it" uses the same `if` as the render step. It runs after the render and before both `agentcore deploy` steps, and copies the root `Dockerfile` for both agents. This matches `launch.py`, which uses `get_agentcore_directory(Path.cwd(), …)` with `config_path = Path.cwd()/.bedrock_agentcore.yaml`. The build context stays `source_path` (the repo root), and the toolkit passes `-f <copy>` because the copy sits outside the context root. BuildKit finds no `Dockerfile.dockerignore` next to the copy, so the root `.dockerignore` applies. The root Dockerfile's `COPY` set is unchanged, so neither the copies nor the rendered YAML reach the image. Tests `-k dockerfile` green (rerun). |
| AC7 | PASS | Unchanged (rerun). |
| AC8 | PASS | Unchanged (rerun). |
| AC9 | PASS | Unchanged. Two `AWS::IAM::ManagedPolicy` resources, `cdk-exec-airadar` and `cdk-exec-airadar-2`, both outside `AiRadar*`. Outputs `ExecutionPolicyArn1` and `ExecutionPolicyArn2`. |
| AC10 | PASS | The deploy job masks `vars.CHAT_API_ID` and the derived URL before any `cdk deploy`, and stops with `exit 1` when the variable is empty. The step contains no read and no suppression. Tests `-k mask_deploy` green (rerun). The smoke job's mask is still fail-open, but I found no leak path (F10). |
| AC11 | PASS | Runbook re-read: two-ARN re-bootstrap, rollback replacing both with `AdministratorAccess`, CI-access deploy in `uv sync --group infra` + `uv run cdk` form, the human decisions in the risk register. One stale sentence about `CHAT_API_ID` (F11). |
| AC12 | PASS | Feed-api CORS command repaired (note moved above the block). `tests/test_readme_runbooks.py` green, and the auditor's all-block scan is clean. Infra and harny workflows untouched, templates unchanged (rerun). |
| AC13 | PASS offline; live pending | Two policies, each under the limit. The handler snapshot is faithful and every handler permission is allowed or omitted with a reason. The four human decisions are implemented exactly: `GetSecretValue` only on `secret:ai-radar/tavily-api-key-*`; item actions only on `table/ai-radar-cards` and `…/index/feed-by-score`; `DeleteTable`/`DeleteTableReplica` not allowed, with the omission recorded and the `ai-radar-cards` deny kept; no `iam:CreateServiceLinkedRole`. The resource-coverage test checks every physical name (F3 closed). The denies cover the CI roles, the OIDC provider, `cdk-hnb659fds-*` and both execution policies. LOW notes: F12, F13, F14. Live proof: O12b/e/h. |
| AC14 | PASS | Unchanged (rerun). |
| AC15 | PASS | Unchanged (rerun). |
| AC16 | PASS | Unchanged (rerun). |

## Binding-constraint compliance (round 2)
Every round-1 constraint still holds (rerun). The revision-3 constraints:

| Constraint | Status | Evidence |
|---|---|---|
| Agent Dockerfile placement (revision 3): `mkdir -p` plus a copy of the root `Dockerfile` for both agents before each `agentcore deploy`; renderer and `source_path` unchanged; no second committed Dockerfile | PASS | Workflow step and the reproduction above. `scripts/ci/agentcore_config.py` and the template are unchanged. No new Dockerfile is committed. |
| Deploy job masks from `vars.CHAT_API_ID` and fails closed (no `\|\| true`, no `2>/dev/null` on the read) | PASS | The read was removed and the mask comes from the variable, with `exit 1` when it is empty. This satisfies the "no suppression" wording, and the variable-based mask covers the ChatApiUrl output string. Residual: a stale variable (F11). |
| One or two execution policies, each < 6,144 characters, both outside `AiRadar*`, both passed to bootstrap; denies on both policies (`policy/cdk-exec-airadar*`) | PASS | 4,480 and 3,264 characters. The deny lists both exact policy ARNs, which is equivalent to the pattern. The README and O12b bootstrap with `"<arn1>,<arn2>"`. |
| Handler completeness from a committed snapshot with an omission list | PASS | Snapshot faithful; coverage recomputed; reasons valid for the current templates. |
| IAM writes only on `role/AiRadar*`, `policy/AiRadar*`, `user/ai-radar-chat-api-caller` | PASS | The new `iam:AttachUserPolicy`/`DetachUserPolicy` act on the caller user, conditioned on `iam:PolicyARN` `ArnLike policy/AiRadar*`. The execution policies grant no `iam:CreatePolicy`, so no such policy can exist unless a human creates one, and the grant is inert today. |
| No `"*"` action; no whole-service wildcard on `"*"` | PASS | `dynamodb:Describe*` is on `table/ai-radar-*`, not `*`. |

## Test coverage
| AC | Test | Status |
|---|---|---|
| AC1 | `tests/test_ci_workflows.py` (`test_checks_workflow_*`) | PASS |
| AC2 | `tests/test_ci_workflows.py` (`test_diff_*`, no `pull_request_target`); `tests/test_infra_ci_bootstrap.py` (`test_diff_role_*`) | PASS |
| AC3 | `tests/test_ci_workflows.py` (`test_deploy_trigger_*`); `tests/test_infra_ci_bootstrap.py` (`test_deploy_role_*`) | PASS |
| AC4 | `tests/test_ci_workflows.py` (concurrency); `tests/test_ci_deploy_plan.py` (`test_base_case_*`) | PASS |
| AC5 | `tests/test_ci_deploy_plan.py`; `tests/test_ci_workflows.py` (`test_plan_gates_*`, `-k dockerfile`) | PASS |
| AC6 | `tests/test_ci_workflows.py` (`test_invariant_*`, `-k dockerfile`: path computed with the toolkit's `get_agentcore_directory`, plus detectors for a removed step, a missing agent, a late step and a wrong source); `tests/test_ci_deploy_context.py`; `tests/test_ci_schedule_guard.py`; `tests/test_ci_agentcore_config.py` | PASS |
| AC7 | `tests/test_ci_workflows.py` (`test_smoke_*`); `tests/test_ci_smoke.py`; `tests/test_chat_api_smoke.py` | PASS |
| AC8 | `tests/test_infra_ci_bootstrap.py` (`test_smoke_role_*`, `test_deploy_role_cannot_call_the_chat_route`) | PASS |
| AC9 | `tests/test_infra_ci_bootstrap.py`; `tests/test_ci_workflows.py` | PASS |
| AC10 | `tests/test_ci_workflows.py` (`test_mask_*`, `-k mask_deploy` with four detector fixtures); `tests/test_ci_smoke.py` | PASS |
| AC11 | docs review (auditor) | PASS (F11 LOW) |
| AC12 | existing suite; template comparison; `tests/test_readme_runbooks.py` | PASS |
| AC13 | `tests/test_infra_ci_cfn_exec_policy.py` (`-k coverage`, `-k resource_coverage`, `-k shape`); `tests/test_infra_ci_policy_size.py` (per policy); fixtures `tests/fixtures/cfn/*` | PASS |
| AC14 | `tests/test_ci_repo_protection.py`; the check-name cross-check | PASS |
| AC15 | `tests/test_ci_deploy_context.py` | PASS |
| AC16 | `tests/test_ci_workflows.py` (`test_hardening_*`) | PASS |

Red evidence for the repair tests is recorded in `tasks.md` (O14, O15, O17, O18) and fails for the
right reasons. O16 has no red by design: today's names already match, and the detector fixtures (an
`other-fn` Lambda and a generated-name Lambda) show it fails. `tests/test_infra_ci_policy_size.py`
(keep, round 1) now checks each policy.

### Tier Results
| Tier | Tests found | ACs verified | Setup matches § Validation | Ran | Status | Finding |
|---|---|---|---|---|---|---|
| unit (static YAML) | `tests/test_ci_workflows.py` | AC1–AC10, AC14, AC16 | yes (`pyyaml` in `dev`) | rerun (green) | PASS | — |
| lint (actionlint) | `lint` job step in `backend-checks.yml` | AC1 | yes (pinned, checksum-verified, CI-only) | not run by the auditor (binary download blocked in this session); reused: executor's actionlint 1.7.12 and shellcheck 0.11.0 over all five files, exit 0 (O19) | PASS (reused) | F7 closed on reused evidence |
| unit (CDK synth) | `tests/test_infra_ci_bootstrap.py`, `tests/test_infra_ci_cfn_exec_policy.py`, `tests/test_infra_ci_policy_size.py`, `tests/test_ci_schedule_guard.py` | AC2, AC3, AC6, AC8, AC9, AC13 | yes (committed handler snapshot and omission list, as revision 3 names) | rerun (green) | PASS | F13 (strength, LOW) |
| unit | `tests/test_ci_deploy_plan.py`, `tests/test_ci_agentcore_config.py`, `tests/test_ci_smoke.py`, `tests/test_chat_api_smoke.py`, `tests/test_ci_repo_protection.py` | AC4–AC7, AC10, AC14 | yes | rerun (green) | PASS | — |
| unit (+ CDK synth) | `tests/test_ci_deploy_context.py` | AC6, AC15 | yes | rerun (green) | PASS | — |
| unit (static text) | `tests/test_readme_runbooks.py` | AC12 | yes (none) | rerun (green) | PASS | — |
| integration (synth comparison) + regression | template comparison; full suite | AC12 | yes | rerun (823 passed; infra diff empty) | PASS | — |
| docs review | README "Backend CI/CD" | AC11 | n/a | auditor review | PASS | F11 |
| live (human-only) | none (by design) | AC1–AC3, AC6–AC10, AC13–AC15 | n/a | not run: human-only (O12) | N/A | F8 |

No test sits at a tier that § Validation does not name. No setup was added beyond what revision 3
names (`pyyaml`, the two fixture files).

## Conventions and feedback
- `harny-standards` (CLAUDE.md Conventions, `docs/architecture-principles.md`): no change since
  round 1. The repair adds no plane import and no dependency, and uses uv only. PASS.
- `harny-feedback`: since the conductor's out-of-scope switch to `uv run` (harny#12), the hook can
  resolve ruff and mypy. The auditor's reruns are clean. The CI run of `harny-feedback.yml` and of the
  new workflows is **unavailable** (nothing pushed).

## Privilege and first-deploy review (round 2)
- **Denies across both policies.** IAM evaluates the union of all identity policies attached to
  the CloudFormation execution role, and an explicit deny in either policy overrides an allow in the
  other. The denies in `cdk-exec-airadar-2` therefore bind every action the role takes. No allow pattern matches a
  CI role, `cdk-hnb659fds-*` or either `cdk-exec-airadar*` policy (shape test rerun). The role cannot
  create managed policies (no `iam:CreatePolicy`), cannot attach any managed policy to a role except
  `AWSLambdaBasicExecutionRole`, and cannot touch the OIDC provider.
- **Residual escalation path** (unchanged, accepted, recorded in the README risk register and as the
  permissions-boundary follow-up). A merged template can still create an `AiRadar*` role with an
  arbitrary inline policy and trust (`iam:PutRolePolicy`, `iam:UpdateAssumeRolePolicy`, `iam:PassRole`
  on `role/AiRadar*`) and attach it to a Lambda or a schedule. The PR ruleset, `CODEOWNERS` and the PR
  diff are the controls. The repair adds no new path of this kind.
- **The `CHAT_API_ID` guard and the first deploy.** The deploy job now stops when
  `vars.CHAT_API_ID` is empty. That does not block the first deploy: the README bootstrap sets the
  variable in step 2, before the first live run in step 5, and the job prints a clear stop message.
  The README still describes the variable as "used only to mask the id in PR logs" (F11).
- **The smoke job's fail-open mask** (`2>/dev/null || true`, left unchanged). I found no leak path. The
  step prints nothing itself. `scripts/ci/smoke.py` emits `::add-mask::` for the URL and the id from
  its own stack read before printing anything, and if that read fails it raises before any URL is
  known. It only prints statuses, and its HTTP errors return `0, ""`. Rated LOW as defense in depth (F10).
- **First-deploy risks that remain (live only).** The deploy-role allow-list for `agentcore deploy`
  (O12h). Any handler call the snapshot under-reports. The IAM User read and delete handlers, which may
  call the omitted read-only `iam:ListGroupsForUser`/`iam:GetLoginProfile` (F14). Rollback to
  `AdministratorAccess` is documented. I found nothing that could flip the schedule, pass other context,
  deploy an agent without `-a`, or revert the CORS origin.

## Findings
| Id | Severity | Cites | Finding | Closure condition | Status |
|---|---|---|---|---|---|
| F1 | CRITICAL | AC5, AC6 | `--local-build` needs `.bedrock_agentcore/<agent>/Dockerfile`, which is absent in CI (round 1). | Root Dockerfile placed for both agents before deploy, plus a test using the toolkit's path function. | **Closed** (round 2: workflow step, `-k dockerfile` tests, auditor reproduction) |
| F2 | HIGH | AC13 | The execution policy was missing actions that the CloudFormation handlers need (round 1). | Every handler permission allowed or omitted with a reason; under the size limit. | **Closed offline** (round 2: snapshot faithful, coverage recomputed, 4,480/3,264 characters). Live confirmation stays in O12e/h. |
| F3 | MEDIUM | AC13 | The coverage test ignored resource scoping (round 1). | Resource-coverage test with a failing fixture. | **Closed** (round 2; one primary action per type, see F13) |
| F4 | MEDIUM | AC12 | A comment inside a continued README command (round 1). | Command repaired. | **Closed** (round 2: fixed; test plus the auditor's all-block scan) |
| F5 | MEDIUM | AC10 | The deploy-job mask was fail-open (round 1). | Mask from `vars.CHAT_API_ID`, fail closed. | **Closed** (round 2) |
| F6 | MEDIUM | tasks.md | `tasks.md` was stale (round 1). | Updated. | **Closed** (round 2; leftovers in F15) |
| F7 | LOW | AC1 lint tier | actionlint did not cover all workflows with shellcheck (round 1). | Run over all five with shellcheck and record it. | **Closed on reused evidence** (O19; not re-run by the auditor) |
| F8 | LOW | live rows | Live tiers not run (human-only). | O12 (a)–(i) recorded. | Open (expected) |
| F9 | LOW | AC11 | CI-access deploy command not in `uv run` form (round 1). | `uv run cdk` form. | **Closed** (round 2) |
| F10 | LOW | AC10 | The smoke job's mask step still reads `ChatApiUrl` with `2>/dev/null \|\| true`. No leak path found (see above), but it is inconsistent with the deploy job. | Also mask from `vars.CHAT_API_ID` in the smoke job (and/or drop the suppression). | Open |
| F11 | LOW | AC11, AC10 | README bootstrap step 2 says `CHAT_API_ID` is "used only to mask the id in PR logs". The deploy job now requires it (it stops when it is unset), and since the job no longer reads the live output, a stale value after an API id change would leave a new URL unmasked in the deploy log. | README step 2 says the deploy job stops without it and that it must be updated if the chat API id ever changes. | Open |
| F12 | LOW | AC13 (binding: "`*` only where unscopable") | Of the executor's `Resource: "*"` grants, `cloudwatch:PutMetricData`, `secretsmanager:GetRandomPassword`, `logs:DescribeLogGroups`, `logs:DescribeResourcePolicies` and `logs:DescribeIndexPolicies` have no resource-level support (genuinely `*`). `logs:PutResourcePolicy`/`logs:DeleteResourcePolicy` are account-level writes. The handler uses them only for a LogGroup `ResourcePolicyDocument`, which no template sets, so they would be better omitted with a reason than allowed on `*`. `billing:GetBillingViewData` is used only with a `BillingViewArn`, which the budget does not set; omit it, or scope it to the account's billing views if IAM supports that. None of these was a human decision. | Move the unused account-level writes (and the unused billing read) to the omission list, or record why they must stay. | Open |
| F13 | LOW | AC13 (test strength) | (a) The omission patterns are global wildcards (`s3:*`, `ec2:*`, `kms:*`, `iam:*Group*`, …), not tied to a resource type, so a future type that genuinely needs one of them is silently "omitted". This is mitigated because any new type must first enter the reviewed snapshot. (b) The resource-coverage rule checks one primary action per type. Narrower secondary statements (DynamoDB item actions, `GetSecretValue`) are not checked against new resources. Both are acceptable today. | Optionally key omissions by resource type and check secondary actions in narrower statements. | Open (recommendation) |
| F14 | LOW | AC13 (live risk) | The `AWS::IAM::User` read and delete handlers list read-only `iam:ListGroupsForUser` and `iam:GetLoginProfile`, which the `iam:*Group*` and `iam:*LoginProfile` omissions drop. If the handler calls them unconditionally, any update, drift check or delete of the caller user fails with `AccessDenied`. That is recoverable, and the user changes rarely. | Allow these two read-only actions on `user/ai-radar-chat-api-caller` (small size cost), or confirm on the first live run (O12h). | Open |
| F15 | LOW | tasks.md | The Finding responses table still carries the stale "Red test bug (O3)" row ("11 passed, 1 failed"). O12(a) says to record "the three role ARNs", but the runbook needs five repository variables (`AWS_DIFF_ROLE_ARN`, `AWS_DEPLOY_ROLE_ARN`, `AWS_SMOKE_ROLE_ARN`, `AWS_ACCOUNT_ID`, `CHAT_API_ID`). | Mark the O3 row resolved; align O12(a) with README step 2. | Open |

The round-1 findings are kept in full under "Round 1 record".

## Audit log
| Round | Date | Verdict | Notes |
|---|---|---|---|
| 1 | 2026-10-27 | REJECTED | F1 CRITICAL, F2 HIGH, F3–F6 MEDIUM, F7–F9 LOW. 783 passed. |
| 2 | 2026-10-28 | APPROVED WITH RESERVATIONS | F1–F7 and F9 closed (F2 offline, F7 on reused evidence). New: F10–F15, all LOW. 823 passed; ruff and mypy clean; infra untouched; snapshot faithful; policies 4,480/3,264 characters. Live O12 pending. |

## Final verdict

APPROVED WITH RESERVATIONS

**Summary**: The round-1 blockers are fixed and independently confirmed. The agent Dockerfile is now
where the locked toolkit reads it, for both agents. The CloudFormation execution permissions are
split into two policies that cover every handler permission (or omit it with a sound reason) and
implement the four human decisions exactly. The README runbook is repaired. The deploy-job mask
fails closed. What remains is LOW and the human-only live verification.

**Critical Issues** (must fix before merge):
- None.

**Warnings** (should fix, not blocking):
- F11: correct the README's `CHAT_API_ID` description (the deploy job requires it; update it if the API id changes).
- F12: omit `logs:PutResourcePolicy`/`DeleteResourcePolicy` and `billing:GetBillingViewData` instead of allowing them on `*`, or record why they must stay.
- F14: allow read-only `iam:ListGroupsForUser`/`iam:GetLoginProfile` on the caller user, or watch for them in O12h.
- F10: mask from `vars.CHAT_API_ID` in the smoke job as well.
- F15: tidy the two stale `tasks.md` lines.

**Recommendations** (nice to have):
- F13: key omissions by resource type; check secondary narrow-scoped actions in the resource-coverage test.
- Consider `allowed-account-ids` on `configure-aws-credentials` as a second account guard, and Dependabot for `github-actions`.

**Remaining human-only steps (O12, in order):**
- (a) Deploy the CI access stack with admin credentials and `-c chat_api_id=…`, then set the five repository variables.
- (b) Re-bootstrap CDK with `--cloudformation-execution-policies "<ExecutionPolicyArn1>,<ExecutionPolicyArn2>"`. `cdk synth` and `cdk diff` of all seven stacks show no differences. Keep the `AdministratorAccess` rollback ready.
- (c) Run the protection script as a dry run, then `--apply`, then the read-back; confirm a direct push is rejected.
- (d) A same-repo PR shows the diff; a fork PR shows the skip line and needs approval.
- (e) First watched deploy: smoke green, runtime ids unchanged, schedule `DISABLED`, budget 500, CORS unchanged, chat URL masked.
- (f) A signed `POST /v1/chat` returns 403 for the deploy role and 200 for the smoke role.
- (g) A docs-only merge reports nothing to deploy.
- (h) Confirm the deploy-role and execution-policy allow-lists from CloudTrail and CloudFormation events, and fix any gap by PR.
- (i) The Vercel origin, by PR, when the project exists.

**Documentation step (after this gate, not audited here):** ADRs 0040–0047 (including the ADR 0028
amendment, 0043), the `specs/current/` updates (`runtime-deployment`, `scheduling`, `chat-api-auth`,
`feed-api`, a new `ci-cd`), `CHANGELOG`, CLAUDE.md "Current state" and the README spec tables.

---

## Round 1 record (2026-10-27, REJECTED; kept for history)

Round 1 reviewed the full change against revision 2. The suite gave 783 passed, including in a
clean env with no AWS config. ruff and mypy were clean. The infra and harny workflows were untouched,
and the seven templates were identical with the pinned and the earlier runbook context. The pinned
action SHAs were verified with `git ls-remote`, and their inputs against each `action.yml`. The GitHub
REST endpoints and payloads were verified against the OpenAPI description. The CloudFormation registry
schemas were compared with the policy, and the toolkit 0.3.10 local-build path was read.

Round 1 AC status: AC1–AC4 and AC7–AC11 and AC14–AC16 PASS. AC5 and AC6 PARTIAL (F1). AC12 PARTIAL
(F4). AC13 PASS offline but at risk live (F2, F3). AC10 PASS with F5.

Round 1 findings, as written then:
- **F1 (CRITICAL; AC5, AC6).** In toolkit 0.3.10, `--local-build` resolves the Dockerfile as
  `get_agentcore_directory(cwd, agent, source_path)/Dockerfile`. When `source_path` is set, that is
  `<workspace>/.bedrock_agentcore/<agent>/Dockerfile`, and the toolkit raises "Dockerfile not found …
  run 'agentcore configure' first" when it is missing. That directory is gitignored, so every
  agent-selecting deploy (and the first run) would fail mid-deploy. The CodeBuild path falls back to
  the root `Dockerfile`; the local-build path does not.
- **F2 (HIGH, AC13).** The policy lacked handler actions: Lambda code-signing, runtime-management,
  recursion and scaling config; `sns:ListSubscriptionsByTopic`/`GetDataProtectionPolicy`;
  `dynamodb:GetResourcePolicy`; logs describe-policy actions; budgets tag actions;
  `iam:UpdateRoleDescription`. It was at 5,742 of 6,144 characters, and `REQUIRED_ACTIONS` was a
  hand-picked subset.
- **F3 (MEDIUM, AC13).** The coverage test matched action names only, so an out-of-pattern resource
  name would pass offline and fail live.
- **F4 (MEDIUM, AC12).** Comment lines inside the backslash-continued feed-api CORS `cdk deploy`
  command (README around line 873) cut it short.
- **F5 (MEDIUM, AC10).** The deploy-job mask was fail-open (`2>/dev/null || true`), with no
  `vars.CHAT_API_ID` mask.
- **F6 (MEDIUM).** `tasks.md` was stale: Status line, O3, O11, Working state, and O9/O10 evidence.
- **F7 (LOW).** actionlint was run on three workflows without shellcheck, and not re-run by the auditor.
- **F8 (LOW).** Live tiers human-only.
- **F9 (LOW).** The README CI-access command was not in `uv run` form.

Round 1 notes that still stand:
- `tests/test_infra_ci_policy_size.py`: keep.
- The `tests/test_ci_agentcore_config.py` fix (`["cwd","out"]`) is legitimate and not weakened.
- OIDC trust is exact `StringEquals` on aud and sub.
- The toolkit takes the update path when `agent_id` is set, and the deploy role has no `CreateAgentRuntime`.
- `ubuntu-24.04-arm` ships the AWS CLI, Docker and Buildx.
- Out of scope: the conductor's `uv run` hook change (harny#12) and the merged test-speed work.

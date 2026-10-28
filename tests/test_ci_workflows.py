"""Static checks of the backend CI/CD workflows, `CODEOWNERS` and the ruleset check names
(spec backend-cicd-pipeline, outcome O8; AC1-AC10, AC14, AC16).

Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation rows AC1, AC2, AC3, AC4, AC5,
AC6, AC7, AC8, AC9, AC10, AC14 (check-name cross-check) and AC16. These parse the YAML with
PyYAML and assert on its structure (triggers, `needs`, `if`, permissions, step order); they do
not grep source for style. `actionlint` is a separate lint tier, not run from here.

Layout the implementation must follow (the plan leaves names open; chosen by the test writer):
- `.github/workflows/backend-checks.yml`: reusable (`workflow_call`) checks.
- `.github/workflows/backend-pr.yml`: jobs `checks` (calls the reusable workflow) and `diff`.
- `.github/workflows/backend-deploy.yml`: jobs `checks`, `plan`, `deploy`, `smoke`.
- The `cdk` wrapper is `scripts/ci/cdk.py` (or `python -m scripts.ci.cdk`); the planner, smoke
  runner, schedule guard and origin validation are `scripts.ci.deploy_plan`, `scripts.ci.smoke`,
  `scripts.ci.schedule_guard` and `scripts.ci.deploy_context`.
- AWS roles are chosen with `${{ vars.* }}` (repository variables), never secrets. The account
  guard is a step that calls `get-caller-identity`; the account id itself is not pinned here.

RED phase: none of the backend workflows or `CODEOWNERS` exist yet.
"""
from __future__ import annotations

import copy
import fnmatch
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
from ci_synth_helpers import REPO, load  # type: ignore[import-not-found]

yaml = load("yaml")

WORKFLOWS = REPO / ".github" / "workflows"
CHECKS = WORKFLOWS / "backend-checks.yml"
PR = WORKFLOWS / "backend-pr.yml"
DEPLOY = WORKFLOWS / "backend-deploy.yml"
CODEOWNERS = REPO / ".github" / "CODEOWNERS"
CHECKS_USES = "./.github/workflows/backend-checks.yml"

WRAPPER = r"scripts[/.]ci[/.]cdk(?:\.py)?"
RAW_CDK = re.compile(r"(?:^|[\s;&|(])(?:npx\s+)?cdk\s+(?:synth|diff|deploy|bootstrap|destroy|list|ls|doctor)\b")
AGENTCORE = re.compile(r"\bagentcore\s+(?:deploy|status|invoke|configure|destroy|launch|create)\b")


# --- helpers -----------------------------------------------------------------------------------


def _wf(path: Path) -> dict[str, Any]:
    assert path.is_file(), f"{path.relative_to(REPO)} does not exist"
    return dict(yaml.safe_load(path.read_text()))


def _triggers(wf: dict[str, Any]) -> dict[str, Any]:
    raw: dict[Any, Any] = wf
    on = raw.get("on", raw.get(True))  # PyYAML (YAML 1.1) reads the key `on` as True
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return dict(on or {})


def _jobs(wf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return dict(wf["jobs"])


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return list(job.get("steps", []))


def _logical_lines(run: str) -> list[str]:
    joined = run.replace("\\\n", " ")
    return [ln.strip() for ln in joined.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _run_lines(wf: dict[str, Any]) -> list[str]:
    return [ln for job in _jobs(wf).values() for s in _steps(job) for ln in _logical_lines(s.get("run", ""))]


def _job_run_text(job: dict[str, Any]) -> str:
    return "\n".join(s.get("run", "") for s in _steps(job))


def _backend_workflows() -> list[Path]:
    found = sorted(WORKFLOWS.glob("backend-*.yml"))
    assert {p.name for p in found} >= {"backend-checks.yml", "backend-pr.yml", "backend-deploy.yml"}
    return found


def _needs(job: dict[str, Any]) -> list[str]:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


def _needs_closure(jobs: dict[str, dict[str, Any]], job_id: str) -> set[str]:
    seen: set[str] = set()
    todo = _needs(jobs[job_id])
    while todo:
        n = todo.pop()
        if n not in seen:
            seen.add(n)
            todo.extend(_needs(jobs[n]))
    return seen


def _aws_creds_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in _steps(job) if str(s.get("uses", "")).startswith("aws-actions/configure-aws-credentials")]


def _role_expr(job: dict[str, Any]) -> str:
    steps = _aws_creds_steps(job)
    assert len(steps) == 1
    return str(steps[0]["with"]["role-to-assume"])


def _permissions(node: dict[str, Any]) -> dict[str, str]:
    perms = node.get("permissions")
    return dict(perms) if isinstance(perms, dict) else {}


def _job_with_run(wf: dict[str, Any], pattern: str) -> tuple[str, dict[str, Any]]:
    hits = [(i, j) for i, j in _jobs(wf).items() if re.search(pattern, _job_run_text(j))]
    assert len(hits) == 1, f"expected exactly one job running /{pattern}/, got {[i for i, _ in hits]}"
    return hits[0]


# --- AC1: the checks workflow ------------------------------------------------------------------


def test_checks_workflow_is_reusable_and_runs_the_five_checks():
    wf = _wf(CHECKS)
    assert "workflow_call" in _triggers(wf)
    lines = "\n".join(_run_lines(wf))
    assert re.search(r"\bpytest\b", lines)
    assert re.search(r"\bruff check\b", lines)
    assert re.search(r"\bmypy\b", lines)
    assert re.search(r"\bactionlint\b", lines)
    assert re.search(WRAPPER + r"\s+synth\b", lines)


def test_checks_workflow_validates_the_context_before_synth_and_runs_the_schedule_guard_after_it():
    wf = _wf(CHECKS)
    texts = [
        (job_id, i, s.get("run", ""))
        for job_id, job in _jobs(wf).items()
        for i, s in enumerate(_steps(job))
    ]

    def where(pattern: str) -> tuple[str, int]:
        hits = [(j, i) for j, i, t in texts if re.search(pattern, t)]
        assert hits, pattern
        return hits[0]

    validate, synth, guard = where(r"deploy_context"), where(WRAPPER + r"\s+synth"), where(r"schedule_guard")
    assert validate[0] == synth[0] == guard[0]
    assert validate[1] < synth[1] < guard[1]


def test_checks_workflow_installs_a_frozen_cached_environment():
    wf = _wf(CHECKS)
    uses = [s for j in _jobs(wf).values() for s in _steps(j) if str(s.get("uses", "")).startswith("astral-sh/setup-uv")]
    assert uses and all(str(s["with"].get("enable-cache")).lower() == "true" for s in uses)
    assert re.search(r"uv sync\b.*--frozen", "\n".join(_run_lines(wf)))


def test_checks_workflow_downloads_actionlint_with_a_checksum_verification():
    wf = _wf(CHECKS)
    _, job = _job_with_run(wf, r"actionlint")
    text = _job_run_text(job)
    assert "sha256sum" in text or "shasum" in text


def test_checks_workflow_needs_no_aws_credentials_and_cannot_mint_an_oidc_token():
    wf = _wf(CHECKS)
    assert "id-token" not in _permissions(wf)
    for job in _jobs(wf).values():
        assert "id-token" not in _permissions(job)
        assert _aws_creds_steps(job) == []
        assert not [s for s in _steps(job) if str(s.get("uses", "")).startswith("aws-actions/")]


@pytest.mark.parametrize("path", [PR, DEPLOY])
def test_checks_workflow_is_called_by_the_pr_and_deploy_workflows(path):
    callers = [j for j in _jobs(_wf(path)).values() if j.get("uses") == CHECKS_USES]
    assert len(callers) == 1


# --- AC2: the PR diff -----------------------------------------------------------------------------


def test_every_workflow_avoids_the_pull_request_target_trigger():
    files = sorted(WORKFLOWS.glob("*.yml"))
    assert files
    for path in files:
        assert "pull_request_target" not in _triggers(yaml.safe_load(path.read_text())), path.name


def test_pr_workflow_triggers_on_pull_request_only():
    triggers = _triggers(_wf(PR))
    assert "pull_request" in triggers
    assert not {"push", "pull_request_target", "workflow_run"} & set(triggers)


def test_diff_job_runs_only_for_pull_requests_from_the_same_repository():
    job = _jobs(_wf(PR))["diff"]
    assert "github.event.pull_request.head.repo.full_name == github.repository" in str(job.get("if", ""))


def test_diff_job_compares_templates_through_the_wrapper_and_the_read_only_lookup_path():
    wf = _wf(PR)
    job = _jobs(wf)["diff"]
    lines = [ln for s in _steps(job) for ln in _logical_lines(s.get("run", ""))]
    diffs = [ln for ln in lines if re.search(WRAPPER + r"\s+diff\b", ln)]
    assert diffs
    assert all("--method=template" in ln or "--method template" in ln for ln in diffs)


def test_diff_job_assumes_a_repository_variable_role_and_is_the_only_job_with_an_id_token():
    wf = _wf(PR)
    jobs = _jobs(wf)
    assert "vars." in _role_expr(jobs["diff"])
    assert "secrets." not in _role_expr(jobs["diff"])
    with_token = {i for i, j in jobs.items() if _permissions(j).get("id-token") == "write"}
    assert with_token == {"diff"}
    assert _permissions(wf).get("id-token") != "write"


def test_diff_output_goes_to_the_job_summary_and_fork_prs_get_an_explained_skip():
    wf = _wf(PR)
    jobs = _jobs(wf)
    diff_text = _job_run_text(jobs["diff"])
    assert "GITHUB_STEP_SUMMARY" in diff_text
    skips = []
    for job in jobs.values():
        for step in _steps(job):
            cond = f"{job.get('if', '')} {step.get('if', '')}"
            if "!= github.repository" in cond and "GITHUB_STEP_SUMMARY" in step.get("run", ""):
                skips.append(step["run"])
    assert len(skips) == 1
    assert "diff skipped" in skips[0] and "fork" in skips[0].lower()


# --- AC3: deploy trigger and authentication ------------------------------------------------------------


def test_deploy_trigger_is_a_push_to_main_with_no_pull_request_trigger():
    triggers = _triggers(_wf(DEPLOY))
    assert triggers["push"]["branches"] == ["main"]
    assert not {"pull_request", "pull_request_target"} & set(triggers)
    assert set(triggers) <= {"push", "workflow_dispatch"}


def test_deploy_trigger_deploy_starts_only_after_the_checks_and_has_no_approval_gate():
    jobs = _jobs(_wf(DEPLOY))
    assert "checks" in _needs_closure(jobs, "plan")
    assert {"checks", "plan"} <= _needs_closure(jobs, "deploy")
    for job_id, job in jobs.items():
        assert "environment" not in job, job_id


def test_deploy_trigger_deploy_job_authenticates_through_oidc_with_a_variable_role():
    jobs = _jobs(_wf(DEPLOY))
    assert _permissions(jobs["deploy"]).get("id-token") == "write"
    assert "vars." in _role_expr(jobs["deploy"])
    assert "secrets." not in _role_expr(jobs["deploy"])


def test_deploy_trigger_account_check_precedes_the_first_cdk_or_agentcore_step():
    jobs = _jobs(_wf(DEPLOY))
    steps = _steps(jobs["deploy"])
    first_action = next(
        i for i, s in enumerate(steps)
        if re.search(WRAPPER + r"\s+deploy|" + AGENTCORE.pattern, s.get("run", ""))
    )
    guards = [
        i for i, s in enumerate(steps)
        if "get-caller-identity" in s.get("run", "") and re.search(r"exit\s+1|exit 1", s.get("run", ""))
    ]
    assert guards and min(guards) < first_action
    creds = [i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("aws-actions/configure-aws-credentials")]
    assert creds and min(creds) < min(guards)


# --- AC4 / AC5: concurrency and the plan ------------------------------------------------------------------


def test_deploy_concurrency_is_one_fixed_group_that_never_cancels_a_running_deploy():
    concurrency = _wf(DEPLOY).get("concurrency")
    assert isinstance(concurrency, dict)
    group = str(concurrency["group"])
    assert group and "${{" not in group  # the same group for every run
    assert concurrency["cancel-in-progress"] is False


def test_plan_job_computes_targets_from_the_last_successful_run_and_reports_nothing_to_deploy():
    jobs = _jobs(_wf(DEPLOY))
    plan = jobs["plan"]
    text = _job_run_text(plan)
    assert re.search(r"scripts[/.]ci[/.]deploy_plan", text)
    assert "success" in text  # the base is the last *successful* run, not the parent commit
    assert "nothing to deploy" in text.lower()
    assert _permissions(plan).get("actions") == "read"
    assert plan.get("outputs")


def test_plan_gates_every_deploy_and_smoke_job_on_a_non_empty_plan():
    jobs = _jobs(_wf(DEPLOY))
    for job_id in ("deploy", "smoke"):
        assert "plan" in str(jobs[job_id].get("if", "")), job_id


def test_plan_gates_each_aws_step_so_an_empty_plan_makes_no_deploy_call():
    jobs = _jobs(_wf(DEPLOY))
    for step in _steps(jobs["deploy"]):
        if re.search(WRAPPER + r"\s+deploy|" + AGENTCORE.pattern, step.get("run", "")):
            cond = f"{jobs['deploy'].get('if', '')} {step.get('if', '')}"
            assert "plan" in cond


# --- AC6: deploy invariants ---------------------------------------------------------------------------------


def test_invariant_every_cdk_invocation_goes_through_the_wrapper():
    for path in _backend_workflows():
        for line in _run_lines(_wf(path)):
            assert not RAW_CDK.search(line), f"{path.name}: {line}"
    all_lines = "\n".join(ln for p in _backend_workflows() for ln in _run_lines(_wf(p)))
    for sub in ("synth", "diff", "deploy"):
        assert re.search(WRAPPER + rf"\s+{sub}\b", all_lines), sub


def test_invariant_no_workflow_passes_a_schedule_context_value():
    for path in _backend_workflows():
        text = path.read_text()
        assert not re.search(r"schedule_[a-z_]+\s*=", text), path.name
        assert not re.search(r"(?:-c|--context)\s+schedule_", text), path.name


def test_invariant_deploys_name_their_stacks_with_exclusively():
    deploy_lines = [ln for ln in _run_lines(_wf(DEPLOY)) if re.search(WRAPPER + r"\s+deploy\b", ln)]
    assert deploy_lines
    assert all("--exclusively" in ln for ln in deploy_lines)


def test_invariant_every_agentcore_command_names_its_agent_and_builds_locally():
    lines = [ln for ln in _run_lines(_wf(DEPLOY)) if AGENTCORE.search(ln)]
    assert lines
    for ln in lines:
        assert re.search(r"\s-a[\s=]", ln), ln
    deploys = [ln for ln in lines if re.search(r"\bagentcore\s+deploy\b", ln)]
    assert deploys and all("--local-build" in ln for ln in deploys)


def test_invariant_the_chat_agent_is_deployed_with_its_entrypoint_variable():
    text = "\n".join(_run_lines(_wf(DEPLOY)))
    assert re.search(r"--env\s+AGENT_ENTRYPOINT=chat_app\.py", text)


def test_invariant_ci_never_destroys_configures_or_invokes_anything():
    for path in _backend_workflows():
        for line in _run_lines(_wf(path)):
            assert not re.search(r"\bagentcore\s+(?:destroy|configure|invoke|launch|create)\b", line), line
            assert not re.search(WRAPPER + r"\s+(?:destroy|bootstrap)\b", line), line


def test_invariant_the_ci_access_app_is_never_referenced_by_a_workflow():
    for path in _backend_workflows():
        assert "ci_bootstrap" not in path.read_text(), path.name


# --- AC7 / AC8: smoke job -------------------------------------------------------------------------------------


def test_smoke_job_runs_after_the_deploy_for_any_non_empty_plan_whatever_the_targets():
    jobs = _jobs(_wf(DEPLOY))
    smoke = jobs["smoke"]
    assert "deploy" in _needs_closure(jobs, "smoke")
    conditions = [str(smoke.get("if", ""))] + [str(s.get("if", "")) for s in _steps(smoke)]
    assert "plan" in conditions[0]
    for cond in conditions:
        assert not re.search(r"AiRadar|ai_radar|agent|stack|feed|chat|budget|schedule", cond, re.IGNORECASE), cond


def test_smoke_job_runs_the_smoke_runner_and_never_deploys_or_invokes_agents():
    smoke = _jobs(_wf(DEPLOY))["smoke"]
    text = _job_run_text(smoke)
    assert re.search(r"scripts[/.]ci[/.]smoke", text)
    assert not re.search(WRAPPER + r"\s+(deploy|destroy)", text)
    assert not AGENTCORE.search(text)


def test_smoke_job_uses_its_own_oidc_role_distinct_from_the_deploy_role():
    jobs = _jobs(_wf(DEPLOY))
    assert _permissions(jobs["smoke"]).get("id-token") == "write"
    assert "vars." in _role_expr(jobs["smoke"])
    assert _role_expr(jobs["smoke"]) != _role_expr(jobs["deploy"])


def test_no_workflow_references_a_secret_other_than_the_github_token():
    for path in _backend_workflows():
        text = path.read_text()
        assert set(re.findall(r"secrets\.([A-Za-z0-9_]+)", text)) <= {"GITHUB_TOKEN"}, path.name
        assert not re.search(r"secrets:\s*inherit", text), path.name


# --- AC10: public logs and caches -------------------------------------------------------------------------------


def test_mask_step_precedes_every_step_that_can_print_the_chat_url():
    risky = re.compile(WRAPPER + r"\s+(?:diff|deploy)\b|scripts[/.]ci[/.]smoke|describe-stacks|ChatApiUrl")
    for path in _backend_workflows():
        for job_id, job in _jobs(_wf(path)).items():
            steps = _steps(job)
            for i, step in enumerate(steps):
                run = step.get("run", "")
                if "::add-mask::" in run or not risky.search(run):
                    continue
                assert any("::add-mask::" in s.get("run", "") for s in steps[:i]), f"{path.name}:{job_id}:{step.get('name')}"


def test_mask_step_masks_the_chat_api_output():
    texts = [s.get("run", "") for p in _backend_workflows() for j in _jobs(_wf(p)).values() for s in _steps(j)]
    masking = [t for t in texts if "::add-mask::" in t]
    assert masking
    assert any("ChatApiUrl" in t for t in masking)


def test_mask_no_step_echoes_the_environment_or_enables_shell_tracing():
    for path in _backend_workflows():
        for line in _run_lines(_wf(path)):
            assert not re.search(r"\bset\s+-[A-Za-z]*x|xtrace", line), line
            assert not re.search(r"(?:^|[;&|]\s*)(?:env|printenv)(?:\s|$)", line), line


def test_mask_caches_hold_only_dependencies_and_no_artifact_carries_build_output_or_config():
    for path in _backend_workflows():
        for job in _jobs(_wf(path)).values():
            for step in _steps(job):
                uses = str(step.get("uses", ""))
                assert not uses.startswith("actions/cache"), path.name
                if uses.startswith("actions/upload-artifact"):
                    artifact_path = str(step.get("with", {}).get("path", ""))
                    assert "cdk.out" not in artifact_path
                    assert "bedrock_agentcore" not in artifact_path


# --- AC14: ruleset check names match the workflow job names ------------------------------------------------------


def test_ruleset_required_checks_equal_the_pr_workflow_check_names():
    repo_protection = load("scripts.ci.repo_protection")
    pr_jobs = _jobs(_wf(PR))
    caller_id, caller = next((i, j) for i, j in pr_jobs.items() if j.get("uses") == CHECKS_USES)
    caller_name = caller.get("name", caller_id)
    expected = {f"{caller_name} / {job.get('name', job_id)}" for job_id, job in _jobs(_wf(CHECKS)).items()}
    assert set(repo_protection.REQUIRED_CHECKS) == expected


# --- AC16: public-repository hardening ----------------------------------------------------------------------------


def _owners_for(path: str) -> list[str]:
    assert CODEOWNERS.is_file(), ".github/CODEOWNERS does not exist"
    owners: list[str] = []
    for raw in CODEOWNERS.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        pattern, *who = line.split()
        pattern = pattern.lstrip("/")
        if pattern.endswith("/"):
            hit = path.startswith(pattern)
        else:
            hit = fnmatch.fnmatch(path, pattern) or path.startswith(pattern + "/")
        if hit:
            owners = who  # the last matching pattern wins
    return owners


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/backend-deploy.yml",
        ".github/workflows/backend-pr.yml",
        ".github/workflows/backend-checks.yml",
        ".github/CODEOWNERS",
        "scripts/ci/deploy_plan.py",
        "scripts/ci/repo_protection.py",
        "infra/ci_bootstrap/ci_access_stack.py",
        "scripts/ci/deploy_context.json",
    ],
)
def test_hardening_codeowners_assign_the_pipeline_files_to_the_maintainer(path):
    assert "@Danii2020" in _owners_for(path)


def test_hardening_every_job_that_runs_steps_has_a_timeout():
    for path in _backend_workflows():
        for job_id, job in _jobs(_wf(path)).items():
            if "uses" in job:  # a reusable-workflow call cannot set timeout-minutes
                continue
            assert isinstance(job.get("timeout-minutes"), int), f"{path.name}:{job_id}"


def test_hardening_default_token_permissions_are_read_only_in_every_workflow():
    for path in _backend_workflows():
        assert _permissions(_wf(path)) == {"contents": "read"}, path.name


def test_hardening_only_jobs_that_assume_a_role_can_mint_an_oidc_token():
    for path in _backend_workflows():
        for job_id, job in _jobs(_wf(path)).items():
            if _permissions(job).get("id-token") == "write":
                assert len(_aws_creds_steps(job)) == 1, f"{path.name}:{job_id}"


def test_hardening_third_party_actions_are_pinned_to_a_full_commit_sha():
    for path in _backend_workflows():
        wf = _wf(path)
        for job_id, job in _jobs(wf).items():
            for ref in [job.get("uses"), *[s.get("uses") for s in _steps(job)]]:
                if not ref or str(ref).startswith("./"):
                    continue
                assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", str(ref)), f"{path.name}:{job_id}: {ref}"


# --- audit F1: the Dockerfile that `agentcore deploy --local-build` reads (AC5, AC6) ----------------------
#
# Revision 3. The locked toolkit resolves the local-build Dockerfile as
# `get_agentcore_directory(<config dir>, <agent>, <source_path>) / "Dockerfile"`, i.e.
# `.bedrock_agentcore/<agent>/Dockerfile` beside the rendered config, which is gitignored and so
# absent in CI. The deploy job must create that directory and copy the repo-root Dockerfile there
# before each agent's `agentcore deploy`. The test computes the directory with the toolkit's own
# function, then RUNS the deploy job's steps that precede the agent's deploy step in a scratch
# workspace (with no-op shims for uv, aws, npm, agentcore ...) and checks what landed on disk, so
# it does not depend on how the shell is written (loop, two steps, variables).

AGENT_NAMES = ("ai_radar_curation", "ai_radar_chat")
ROOT_DOCKERFILE = "FROM root-dockerfile-marker\n"
SHIMMED_TOOLS = ("uv", "aws", "agentcore", "npm", "npx", "python", "python3", "gh", "node", "pip", "docker")
FAKE_ACCOUNT = "1" * 12


def _expected_agent_dirs() -> dict[str, str]:
    """Workspace-relative Dockerfile directory per agent, from the toolkit's own function."""
    cfg = load("scripts.ci.agentcore_config")
    toolkit = load("bedrock_agentcore_starter_toolkit.utils.runtime.config")
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        roles = {n: f"arn:aws:iam::{FAKE_ACCOUNT}:role/AiRadar-{n}" for n in AGENT_NAMES}
        cfg.render_config(source_path=workspace, execution_roles=roles, output_dir=workspace)
        config = yaml.safe_load((workspace / ".bedrock_agentcore.yaml").read_text())
        return {
            name: toolkit.get_agentcore_directory(workspace, name, agent["source_path"])
            .relative_to(workspace)
            .as_posix()
            for name, agent in config["agents"].items()
        }


def _is_agent_deploy(step: dict[str, Any], agent: str) -> bool:
    run = step.get("run", "")
    if not re.search(r"\bagentcore\s+deploy\b", run):
        return False
    return agent in run or bool(re.search(r"-a\s+[\"']?\$", run))


def _run_steps_in_scratch_workspace(steps: list[dict[str, Any]], workspace: Path, shims: Path) -> None:
    shims.mkdir()
    for tool in SHIMMED_TOOLS:
        shim = shims / tool
        shim.write_text("#!/bin/sh\nexit 0\n")
        shim.chmod(0o755)
    env = {
        "PATH": f"{shims}:/usr/bin:/bin",
        "HOME": str(workspace),
        "GITHUB_WORKSPACE": str(workspace),
        "GITHUB_SHA": "a" * 40,
        "GITHUB_RUN_ID": "1",
        "GITHUB_STEP_SUMMARY": str(workspace / "summary.md"),
    }
    for step in steps:
        if "run" not in step:
            continue
        step_env = {k: str(v) for k, v in (step.get("env") or {}).items() if "${{" not in str(v)}
        subprocess.run(
            ["bash", "-c", step["run"]],
            cwd=workspace,
            env={**env, **step_env},
            capture_output=True,
            timeout=30,
            check=False,
        )


def _dockerfile_problems(wf: dict[str, Any], expected: dict[str, str]) -> list[str]:
    steps = _steps(_jobs(wf)["deploy"])
    problems: list[str] = []
    for agent, rel_dir in expected.items():
        index = next((i for i, s in enumerate(steps) if _is_agent_deploy(s, agent)), None)
        if index is None:
            problems.append(f"{agent}: no `agentcore deploy` step")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            (workspace / "Dockerfile").write_text(ROOT_DOCKERFILE)
            (workspace / "Dockerfile.chat_api").write_text("FROM wrong-source\n")
            (workspace / "Dockerfile.feed_api").write_text("FROM wrong-source\n")
            _run_steps_in_scratch_workspace(steps[:index], workspace, Path(tmp) / "shims")
            target = workspace / rel_dir / "Dockerfile"
            if not target.is_file():
                problems.append(f"{agent}: {rel_dir}/Dockerfile does not exist before its deploy step")
            elif target.read_text() != ROOT_DOCKERFILE:
                problems.append(f"{agent}: {rel_dir}/Dockerfile is not a copy of the root Dockerfile")
    return problems


def _fixture_deploy_workflow(expected: dict[str, str]) -> dict[str, Any]:
    """A correct minimal deploy job, used to prove the detector flags each broken variant."""
    place = "\n".join(f'mkdir -p "{d}" && cp Dockerfile "{d}/Dockerfile"' for d in expected.values())
    steps: list[dict[str, Any]] = [{"name": "Place Dockerfiles", "run": place}]
    for agent in expected:
        steps.append({"name": f"Update {agent}", "run": f"uv run agentcore deploy -a {agent} --local-build"})
    return {"jobs": {"deploy": {"steps": steps}}}


def test_dockerfile_the_deploy_job_places_the_root_dockerfile_where_the_toolkit_reads_it():
    expected = _expected_agent_dirs()
    assert set(expected) == set(AGENT_NAMES)
    assert _dockerfile_problems(_wf(DEPLOY), expected) == []


def test_dockerfile_detector_accepts_a_correct_step():
    expected = _expected_agent_dirs()
    assert _dockerfile_problems(_fixture_deploy_workflow(expected), expected) == []


def test_dockerfile_detector_flags_a_removed_step():
    expected = _expected_agent_dirs()
    wf = _fixture_deploy_workflow(expected)
    del wf["jobs"]["deploy"]["steps"][0]
    assert len(_dockerfile_problems(wf, expected)) == 2


@pytest.mark.parametrize("missing", AGENT_NAMES)
def test_dockerfile_detector_flags_a_step_that_misses_one_agent(missing):
    expected = _expected_agent_dirs()
    wf = _fixture_deploy_workflow(expected)
    others = {a: d for a, d in expected.items() if a != missing}
    wf["jobs"]["deploy"]["steps"][0]["run"] = "\n".join(
        f'mkdir -p "{d}" && cp Dockerfile "{d}/Dockerfile"' for d in others.values()
    )
    problems = _dockerfile_problems(wf, expected)
    assert len(problems) == 1 and problems[0].startswith(missing)


def test_dockerfile_detector_flags_a_step_placed_after_the_agent_deploy():
    expected = _expected_agent_dirs()
    wf = _fixture_deploy_workflow(expected)
    steps = wf["jobs"]["deploy"]["steps"]
    steps.append(steps.pop(0))  # copy step now last
    assert len(_dockerfile_problems(wf, expected)) == 2


def test_dockerfile_detector_flags_a_source_other_than_the_root_dockerfile():
    expected = _expected_agent_dirs()
    wf = _fixture_deploy_workflow(expected)
    wf["jobs"]["deploy"]["steps"][0]["run"] = wf["jobs"]["deploy"]["steps"][0]["run"].replace(
        "cp Dockerfile ", "cp Dockerfile.chat_api "
    )
    problems = _dockerfile_problems(wf, expected)
    assert len(problems) == 2 and all("not a copy of the root Dockerfile" in p for p in problems)


# --- audit F5: the deploy job's mask fails closed (AC10) ------------------------------------------------------------

SUPPRESSION = re.compile(r"\|\|\s*(?:true\b|:(?=[\s)]|$))|2>\s*/dev/null|2>&-")


def _mask_deploy_problems(wf: dict[str, Any]) -> list[str]:
    steps = _steps(_jobs(wf)["deploy"])
    mask_steps = [i for i, s in enumerate(steps) if "::add-mask::" in s.get("run", "")]
    problems: list[str] = []
    from_var = [i for i in mask_steps if "vars.CHAT_API_ID" in json.dumps(steps[i])]
    if not from_var:
        problems.append("no mask step uses vars.CHAT_API_ID")
    for i in from_var:
        run = steps[i]["run"]
        holders = [k for k, v in (steps[i].get("env") or {}).items() if "vars.CHAT_API_ID" in str(v)]
        direct = re.search(r"add-mask::\$\{\{\s*vars\.CHAT_API_ID\s*\}\}", run)
        via_env = any(re.search(rf"add-mask::\"?\$\{{?{k}\b", run) for k in holders)
        if not (direct or via_env):
            problems.append("vars.CHAT_API_ID is not what the mask step emits `::add-mask::` for")
    for i in mask_steps:
        for line in _logical_lines(steps[i]["run"]):
            if SUPPRESSION.search(line):
                problems.append(f"mask step swallows a failure: {line}")
    first_cdk_deploy = next(
        (i for i, s in enumerate(steps) if re.search(WRAPPER + r"\s+deploy\b", s.get("run", ""))), None
    )
    if first_cdk_deploy is not None and (not from_var or min(from_var) > first_cdk_deploy):
        problems.append("the vars.CHAT_API_ID mask does not precede every cdk deploy")
    return problems


def _fixture_mask_workflow() -> dict[str, Any]:
    return {
        "jobs": {
            "deploy": {
                "steps": [
                    {
                        "name": "Mask",
                        "env": {"CHAT_API_ID": "${{ vars.CHAT_API_ID }}"},
                        "run": (
                            'echo "::add-mask::$CHAT_API_ID"\n'
                            "url=$(aws cloudformation describe-stacks --stack-name AiRadarChatApi \\\n"
                            "  --query x --output text)\n"
                            'echo "::add-mask::$url"\n'
                        ),
                    },
                    {"name": "Deploy", "run": "uv run python -m scripts.ci.cdk deploy --exclusively AiRadarChatApi"},
                ]
            }
        }
    }


def test_mask_deploy_job_masks_from_the_repository_variable_and_fails_closed():
    assert _mask_deploy_problems(_wf(DEPLOY)) == []


def test_mask_deploy_detector_accepts_a_correct_step():
    assert _mask_deploy_problems(_fixture_mask_workflow()) == []


def test_mask_deploy_detector_flags_a_swallowed_read_error():
    for suffix in (" || true", " 2>/dev/null"):
        wf = _fixture_mask_workflow()
        step = wf["jobs"]["deploy"]["steps"][0]
        step["run"] = step["run"].replace("--output text", "--output text" + suffix)
        assert any("swallows" in p for p in _mask_deploy_problems(wf)), suffix


def test_mask_deploy_detector_flags_a_mask_that_does_not_use_the_variable():
    wf = _fixture_mask_workflow()
    step = wf["jobs"]["deploy"]["steps"][0]
    del step["env"]
    step["run"] = step["run"].replace('echo "::add-mask::$CHAT_API_ID"\n', "")
    assert any("vars.CHAT_API_ID" in p for p in _mask_deploy_problems(wf))


def test_mask_deploy_detector_flags_a_mask_placed_after_the_deploy():
    wf = copy.deepcopy(_fixture_mask_workflow())
    steps = wf["jobs"]["deploy"]["steps"]
    steps.append(steps.pop(0))
    assert any("precede" in p for p in _mask_deploy_problems(wf))

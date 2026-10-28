"""Repository-protection script: dry run, apply, idempotency and payloads
(spec backend-cicd-pipeline, outcome O7; AC14).

Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation row AC14 and
"Decision (repository protection)".

Interface (names chosen by the test writer):
`scripts.ci.repo_protection.main(argv: list[str], gh=None) -> int`
- no `--apply`: dry run. Only GET calls are made; stdout shows, for each change it would make,
  the method, the endpoint and the JSON body.
- `--apply`: writes only what differs from the state read first.
- `gh(method, endpoint, body=None) -> Any` is the single injectable runner (default: `gh api`);
  it returns the parsed JSON response. Endpoints are GitHub's REST ones, for `Danii2020/ai-radar`:
  `GET|POST /repos/{r}/rulesets`, `GET|PUT /repos/{r}/rulesets/{id}`, `GET|PATCH /repos/{r}`
  (`security_and_analysis`), `GET|PUT /repos/{r}/actions/permissions/workflow`, and
  `GET|PUT /repos/{r}/actions/permissions/fork-pr-contributor-approval`.
- `REQUIRED_CHECKS: list[str]` and `RULESET_NAME: str` module constants. The required check
  names are cross-checked against the workflow job names in tests/test_ci_workflows.py.

The fake below behaves like GitHub: it stores what is written and returns it on later reads
with extra server-side fields, so idempotency has to ignore those.

RED phase: `scripts.ci.repo_protection` does not exist yet.
"""
from __future__ import annotations

import copy
import re
from typing import Any

import pytest
from ci_synth_helpers import load  # type: ignore[import-not-found]

REPO = "/repos/Danii2020/ai-radar"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class FakeGitHub:
    def __init__(self) -> None:
        self.ruleset: dict[str, Any] | None = None
        self.other_rulesets: list[dict[str, Any]] = []
        self.security: dict[str, Any] = {
            "secret_scanning": {"status": "disabled"},
            "secret_scanning_push_protection": {"status": "disabled"},
        }
        self.workflow_perms: dict[str, Any] = {
            "default_workflow_permissions": "write",
            "can_approve_pull_request_reviews": True,
        }
        self.fork_approval: dict[str, Any] = {"approval_policy": "first_time_contributors_new_to_github"}
        self.calls: list[tuple[str, str, Any]] = []

    # -- the runner -------------------------------------------------------------------------
    def __call__(self, method: str, endpoint: str, body: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, endpoint, copy.deepcopy(body)))
        if method == "GET" and endpoint == f"{REPO}/rulesets":
            listed = [{"id": r["id"], "name": r["name"], "target": r["target"]} for r in self.other_rulesets]
            if self.ruleset:
                listed.append({"id": self.ruleset["id"], "name": self.ruleset["name"], "target": "branch"})
            return listed
        match = re.fullmatch(rf"{REPO}/rulesets/(\d+)", endpoint)
        if match:
            rid = int(match.group(1))
            if method == "GET":
                for r in [*self.other_rulesets, *([self.ruleset] if self.ruleset else [])]:
                    if r["id"] == rid:
                        return copy.deepcopy(r)
                raise AssertionError(f"unknown ruleset {rid}")
            if method == "PUT":
                assert self.ruleset and self.ruleset["id"] == rid, "PUT to a ruleset that is not ours"
                self.ruleset = self._stored_ruleset(body or {}, rid)
                return copy.deepcopy(self.ruleset)
        if method == "POST" and endpoint == f"{REPO}/rulesets":
            assert self.ruleset is None, "created a second ruleset"
            self.ruleset = self._stored_ruleset(body or {}, 4242)
            return copy.deepcopy(self.ruleset)
        if endpoint == REPO:
            if method == "GET":
                return {"name": "ai-radar", "private": False, "security_and_analysis": copy.deepcopy(self.security)}
            if method == "PATCH":
                for key, value in ((body or {}).get("security_and_analysis") or {}).items():
                    self.security[key] = {"status": value["status"]}
                return {}
        if endpoint == f"{REPO}/actions/permissions/workflow":
            if method == "GET":
                return copy.deepcopy(self.workflow_perms)
            if method == "PUT":
                self.workflow_perms = copy.deepcopy(body or {})
                return {}
        if endpoint == f"{REPO}/actions/permissions/fork-pr-contributor-approval":
            if method == "GET":
                return copy.deepcopy(self.fork_approval)
            if method == "PUT":
                self.fork_approval = copy.deepcopy(body or {})
                return {}
        raise AssertionError(f"unexpected GitHub call: {method} {endpoint}")

    @staticmethod
    def _stored_ruleset(body: dict[str, Any], rid: int) -> dict[str, Any]:
        stored = copy.deepcopy(body)
        stored.update({"id": rid, "source_type": "Repository", "source": "Danii2020/ai-radar",
                       "node_id": "RRS_fake", "created_at": "2026-10-27T00:00:00Z",
                       "updated_at": "2026-10-27T00:00:00Z", "current_user_can_bypass": "never"})
        return stored

    # -- views for assertions -------------------------------------------------------------------
    @property
    def writes(self) -> list[tuple[str, str, Any]]:
        return [c for c in self.calls if c[0] in WRITE_METHODS]

    def rule(self, rule_type: str) -> dict[str, Any]:
        assert self.ruleset
        found = [r for r in self.ruleset["rules"] if r["type"] == rule_type]
        assert len(found) == 1, f"expected one {rule_type} rule, got {found}"
        return found[0]


@pytest.fixture
def prot():
    return load("scripts.ci.repo_protection")


@pytest.fixture
def gh():
    return FakeGitHub()


# --- dry run ---------------------------------------------------------------------------------------


def test_dry_run_makes_no_write_call_and_leaves_the_state_unchanged(prot, gh):
    assert prot.main([], gh=gh) == 0
    assert gh.writes == []
    assert gh.ruleset is None
    assert gh.security["secret_scanning"]["status"] == "disabled"
    assert gh.workflow_perms["default_workflow_permissions"] == "write"


def test_dry_run_prints_each_intended_change_with_its_endpoint_and_json(prot, gh, capsys):
    prot.main([], gh=gh)
    out = capsys.readouterr().out
    assert f"{REPO}/rulesets" in out
    assert f"{REPO}/actions/permissions/workflow" in out
    assert "secret_scanning_push_protection" in out
    assert "non_fast_forward" in out
    assert prot.RULESET_NAME in out


# --- apply: the ruleset ----------------------------------------------------------------------------------


def test_apply_creates_a_ruleset_on_main_with_the_required_rules_and_no_bypass(prot, gh):
    prot.main(["--apply"], gh=gh)
    rs = gh.ruleset
    assert rs
    assert rs["name"] == prot.RULESET_NAME
    assert rs["target"] == "branch"
    assert rs["enforcement"] == "active"
    assert rs["conditions"]["ref_name"]["include"] == ["refs/heads/main"]
    assert rs["bypass_actors"] == []
    assert {r["type"] for r in rs["rules"]} == {"pull_request", "required_status_checks", "non_fast_forward", "deletion"}


def test_apply_requires_the_check_jobs_and_an_up_to_date_branch(prot, gh):
    prot.main(["--apply"], gh=gh)
    params = gh.rule("required_status_checks")["parameters"]
    assert params["strict_required_status_checks_policy"] is True
    assert [c["context"] for c in params["required_status_checks"]] == list(prot.REQUIRED_CHECKS)
    assert len(prot.REQUIRED_CHECKS) >= 1


def test_apply_requires_a_pull_request_without_blocking_a_solo_maintainer(prot, gh):
    prot.main(["--apply"], gh=gh)
    params = gh.rule("pull_request")["parameters"]
    assert params["required_approving_review_count"] == 0
    assert params["require_code_owner_review"] is False


# --- apply: repository settings ---------------------------------------------------------------------------------


def test_apply_enables_secret_scanning_and_push_protection(prot, gh):
    prot.main(["--apply"], gh=gh)
    assert gh.security["secret_scanning"]["status"] == "enabled"
    assert gh.security["secret_scanning_push_protection"]["status"] == "enabled"


def test_apply_makes_the_default_workflow_token_read_only(prot, gh):
    prot.main(["--apply"], gh=gh)
    assert gh.workflow_perms["default_workflow_permissions"] == "read"
    assert gh.workflow_perms["can_approve_pull_request_reviews"] is False


def test_apply_requires_approval_for_all_outside_contributors_workflow_runs(prot, gh):
    prot.main(["--apply"], gh=gh)
    assert gh.fork_approval["approval_policy"] == "all_external_contributors"


# --- idempotency ---------------------------------------------------------------------------------------------------------


def test_second_apply_makes_no_write_call(prot, gh):
    prot.main(["--apply"], gh=gh)
    first_writes = len(gh.writes)
    assert first_writes >= 4
    gh.calls.clear()
    assert prot.main(["--apply"], gh=gh) == 0
    assert gh.writes == []


def test_apply_writes_only_the_ruleset_when_only_the_ruleset_drifted(prot, gh):
    prot.main(["--apply"], gh=gh)
    assert gh.ruleset
    gh.ruleset["rules"] = [
        r for r in gh.ruleset["rules"] if r["type"] != "non_fast_forward"
    ]  # someone removed the force-push rule
    gh.calls.clear()
    prot.main(["--apply"], gh=gh)
    assert [(m, e) for m, e, _ in gh.writes] == [("PUT", f"{REPO}/rulesets/{gh.ruleset['id']}")]
    assert {r["type"] for r in gh.ruleset["rules"]} >= {"non_fast_forward"}


def test_apply_writes_only_the_setting_that_drifted(prot, gh):
    prot.main(["--apply"], gh=gh)
    gh.workflow_perms["default_workflow_permissions"] = "write"
    gh.calls.clear()
    prot.main(["--apply"], gh=gh)
    assert [(m, e) for m, e, _ in gh.writes] == [("PUT", f"{REPO}/actions/permissions/workflow")]


def test_apply_matches_the_ruleset_by_name_and_leaves_other_rulesets_alone(prot, gh):
    gh.other_rulesets = [{"id": 7, "name": "someone-elses", "target": "branch", "rules": [], "enforcement": "active"}]
    prot.main(["--apply"], gh=gh)
    assert gh.ruleset and gh.ruleset["id"] != 7
    assert not any(e.endswith("/rulesets/7") for _, e, _ in gh.writes)


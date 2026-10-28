"""Synth tests for the CI access CDK app: OIDC provider and the diff, deploy and smoke roles
(spec backend-cicd-pipeline, outcome O5; AC2, AC3, AC8, AC9).

Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation rows AC2 (diff role), AC3
(deploy role trust), AC8 (smoke role) and AC9 (access app shape).

Interface (names chosen by the test writer):
- `infra/ci_bootstrap/ci_access_stack.py` defines `CiAccessStack(scope, id)`; it reads the chat
  API id from CDK context `chat_api_id` (never committed) and fails to synthesize without it.
- Every CI role has an explicit `RoleName` that does not start with `AiRadar` / `ai-radar`.
- The stack uses `CliCredentialsStackSynthesizer` (the human deploys it with admin credentials).
- `infra/app.py` does not include it.

The account id is never pinned here: `norm()` replaces any 12-digit id or the
`AWS::AccountId` parameter with `ACCT`, and the region with `REGION`. The chat API id is a
fake.

RED phase: `infra/ci_bootstrap/` does not exist yet.
"""
from __future__ import annotations

import fnmatch
import re
from typing import Any

import pytest
from ci_synth_helpers import (  # type: ignore[import-not-found]
    FAKE_CHAT_API_ID,
    INFRA,
    as_list,
    ci_access_template,
    norm,
    resources_of,
    synth_ci_access,
)

REPO_SLUG = "repo:Danii2020/ai-radar"
SUB_PR = f"{REPO_SLUG}:pull_request"
SUB_MAIN = f"{REPO_SLUG}:ref:refs/heads/main"
BOOTSTRAP_ROLES = [
    f"arn:aws:iam::ACCT:role/cdk-hnb659fds-{kind}-role-ACCT-REGION"
    for kind in ("deploy", "file-publishing", "image-publishing", "lookup")
]
LOOKUP_ROLE = "arn:aws:iam::ACCT:role/cdk-hnb659fds-lookup-role-ACCT-REGION"
RUNTIME_ARNS = {
    "arn:aws:bedrock-agentcore:REGION:ACCT:runtime/ai_radar_curation-FW1w976PCI",
    "arn:aws:bedrock-agentcore:REGION:ACCT:runtime/ai_radar_chat-JFCO0R9lkT",
}


# --- extraction helpers -----------------------------------------------------------------------


def _oidc_conditions(role: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(operator, {flattened-key: value}) for each OIDC web-identity statement of a role."""
    out: list[tuple[str, dict[str, Any]]] = []
    for stmt in role["Properties"]["AssumeRolePolicyDocument"]["Statement"]:
        if "sts:AssumeRoleWithWebIdentity" not in as_list(stmt.get("Action")):
            continue
        for op, cond in stmt.get("Condition", {}).items():
            out.append((op, {norm(k): v for k, v in cond.items()}))
    return out


def _is_oidc_role(role: dict[str, Any]) -> bool:
    return "sts:AssumeRoleWithWebIdentity" in norm(role["Properties"]["AssumeRolePolicyDocument"])


def _sub_of(role: dict[str, Any]) -> str:
    subs = [
        str(v)
        for op, cond in _oidc_conditions(role)
        for k, v in cond.items()
        if k.endswith(":sub")
    ]
    assert len(subs) == 1, subs
    return subs[0]


def _statements(template: dict[str, Any], role_id: str) -> list[dict[str, Any]]:
    """Statements of the inline policies and of every `AWS::IAM::Policy` attached to a role."""
    role = template["Resources"][role_id]
    out: list[dict[str, Any]] = []
    for inline in role["Properties"].get("Policies", []):
        out.extend(inline["PolicyDocument"]["Statement"])
    for policy in resources_of(template, "AWS::IAM::Policy").values():
        refs = [r.get("Ref") for r in as_list(policy["Properties"].get("Roles")) if isinstance(r, dict)]
        if role_id in refs:
            out.extend(policy["Properties"]["PolicyDocument"]["Statement"])
    return out


def _allowed(statements: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(action, normalized resource) pairs of the Allow statements."""
    pairs = []
    for s in statements:
        if s.get("Effect", "Allow") != "Allow":
            continue
        for action in as_list(s.get("Action")):
            for resource in as_list(s.get("Resource")):
                pairs.append((action, norm(resource)))
    return pairs


def _ci_roles(template: dict[str, Any]) -> dict[str, str]:
    """role kind -> logical id, derived from what each OIDC role can do."""
    found: dict[str, str] = {}
    for rid, role in resources_of(template, "AWS::IAM::Role").items():
        if not _is_oidc_role(role):
            continue
        sub = _sub_of(role)
        actions = {a for a, _ in _allowed(_statements(template, rid))}
        if sub == SUB_PR:
            kind = "diff"
        elif "execute-api:Invoke" in actions:
            kind = "smoke"
        else:
            kind = "deploy"
        assert kind not in found, f"two {kind} roles"
        found[kind] = rid
    return found


@pytest.fixture(scope="module")
def template() -> dict[str, Any]:
    return ci_access_template()


@pytest.fixture(scope="module")
def roles(template) -> dict[str, str]:
    return _ci_roles(template)


# --- provider and role set (AC9) -------------------------------------------------------------------


def test_stack_has_exactly_one_github_oidc_provider_for_sts_audience(template):
    providers = resources_of(template, "AWS::IAM::OIDCProvider", "Custom::AWSCDKOpenIdConnectProvider")
    assert len(providers) == 1
    props = {k.lower(): v for k, v in next(iter(providers.values()))["Properties"].items()}
    assert norm(props["url"]).rstrip("/").endswith("token.actions.githubusercontent.com")
    assert as_list(props.get("clientidlist", props.get("clientids"))) == ["sts.amazonaws.com"]


def test_stack_has_exactly_the_three_ci_roles(roles):
    assert set(roles) == {"diff", "deploy", "smoke"}


def test_ci_role_names_are_explicit_and_outside_the_airadar_patterns(template, roles):
    for kind, rid in roles.items():
        name = template["Resources"][rid]["Properties"].get("RoleName")
        assert isinstance(name, str) and name, kind
        assert not name.lower().startswith(("airadar", "ai-radar")), name


def test_every_trust_policy_pins_audience_and_exact_subject_with_string_equals(template, roles):
    for kind, rid in roles.items():
        conds = _oidc_conditions(template["Resources"][rid])
        assert [op for op, _ in conds] == ["StringEquals"], kind  # no StringLike, no other operator
        keys = {k.rsplit(":", 1)[1] for _, c in conds for k in c}
        assert keys == {"aud", "sub"}, kind
        for _, c in conds:
            for k, v in c.items():
                assert "*" not in str(v), kind
                if k.endswith(":aud"):
                    assert v == "sts.amazonaws.com"


def test_no_policy_in_the_stack_allows_a_bare_star_action(template):
    for policy in resources_of(template, "AWS::IAM::Policy", "AWS::IAM::ManagedPolicy").values():
        for stmt in policy["Properties"]["PolicyDocument"]["Statement"]:
            if stmt.get("Effect", "Allow") == "Allow":
                assert "*" not in as_list(stmt["Action"])
    for role in resources_of(template, "AWS::IAM::Role").values():
        for inline in role["Properties"].get("Policies", []):
            for stmt in inline["PolicyDocument"]["Statement"]:
                if stmt.get("Effect", "Allow") == "Allow":
                    assert "*" not in as_list(stmt["Action"])


def test_ci_roles_attach_no_aws_managed_policy(template, roles):
    for kind, rid in roles.items():
        assert "ManagedPolicyArns" not in template["Resources"][rid]["Properties"], kind


def test_template_uses_the_cli_credentials_synthesizer_with_no_bootstrap_dependency(template):
    assert "BootstrapVersion" not in template.get("Parameters", {})
    assert "CheckBootstrapVersion" not in template.get("Rules", {})


def test_the_seven_stack_app_does_not_include_the_ci_access_stack():
    app_source = (INFRA / "app.py").read_text()
    assert "ci_bootstrap" not in app_source
    assert "CiAccessStack" not in app_source


def test_synth_fails_without_the_chat_api_id_context():
    with pytest.raises(Exception):  # noqa: B017 - any failure: a placeholder must never be synthesized
        synth_ci_access(context={})


# --- diff role (AC2) -----------------------------------------------------------------------------------


def test_diff_role_trusts_only_same_repo_pull_request_runs(template, roles):
    assert _sub_of(template["Resources"][roles["diff"]]) == SUB_PR


def test_diff_role_can_only_assume_the_cdk_lookup_role(template, roles):
    pairs = _allowed(_statements(template, roles["diff"]))
    assert pairs
    assert {a for a, _ in pairs} == {"sts:AssumeRole"}
    assert {r for _, r in pairs} == {LOOKUP_ROLE}


# --- deploy role (AC3, AC8) --------------------------------------------------------------------------------


def test_deploy_role_trusts_only_the_main_branch(template, roles):
    assert _sub_of(template["Resources"][roles["deploy"]]) == SUB_MAIN


def test_deploy_role_can_assume_the_four_cdk_bootstrap_roles(template, roles):
    assumed = {r for a, r in _allowed(_statements(template, roles["deploy"])) if a == "sts:AssumeRole"}
    assert set(BOOTSTRAP_ROLES) <= assumed
    assert all(r.startswith("arn:aws:iam::ACCT:role/cdk-hnb659fds-") for r in assumed)


def test_deploy_role_cannot_call_the_chat_route(template, roles):
    actions = {a for a, _ in _allowed(_statements(template, roles["deploy"]))}
    assert not [a for a in actions if fnmatch.fnmatch("execute-api:Invoke", a)]


def test_deploy_role_passes_roles_only_to_agentcore(template, roles):
    passes = [
        s for s in _statements(template, roles["deploy"])
        if s.get("Effect", "Allow") == "Allow" and "iam:PassRole" in as_list(s.get("Action"))
    ]
    assert passes, "agentcore deploy --local-build needs iam:PassRole on the two execution roles"
    for stmt in passes:
        cond = stmt.get("Condition", {}).get("StringEquals", {})
        assert cond.get("iam:PassedToService") == "bedrock-agentcore.amazonaws.com"
        assert all("*" != norm(r) for r in as_list(stmt["Resource"]))


# --- smoke role (AC8) -------------------------------------------------------------------------------------------


def test_smoke_role_trusts_only_the_main_branch(template, roles):
    assert _sub_of(template["Resources"][roles["smoke"]]) == SUB_MAIN


def test_smoke_role_can_invoke_exactly_the_post_chat_route_of_the_given_api(template, roles):
    invokes = [r for a, r in _allowed(_statements(template, roles["smoke"])) if a == "execute-api:Invoke"]
    assert invokes == [f"arn:aws:execute-api:REGION:ACCT:{FAKE_CHAT_API_ID}/*/POST/v1/chat"]


def test_smoke_role_runtime_reads_are_limited_to_the_two_runtimes(template, roles):
    reads = {r for a, r in _allowed(_statements(template, roles["smoke"])) if a == "bedrock-agentcore:GetAgentRuntime"}
    assert reads == RUNTIME_ARNS


def test_smoke_role_can_read_the_two_api_stacks_outputs_and_nothing_wider(template, roles):
    describes = [r for a, r in _allowed(_statements(template, roles["smoke"])) if a == "cloudformation:DescribeStacks"]
    assert describes
    assert all(re.search(r":stack/AiRadar(FeedApi|ChatApi)/", r) for r in describes)


def test_stack_mints_no_long_lived_access_key(template):
    # No long-lived key may be created for GitHub to hold (human decision: OIDC only).
    assert resources_of(template, "AWS::IAM::AccessKey") == {}

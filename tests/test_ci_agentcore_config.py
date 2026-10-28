"""CI AgentCore config renderer (spec backend-cicd-pipeline, outcome O3; AC6, AC12).

Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation row AC6 (rendered agent
config) and the binding constraint "CI never reads or writes the developer's
`.bedrock_agentcore.yaml`".

Interface (names chosen by the test writer):
- `scripts/ci/agentcore.template.yaml`: the committed template (the toolkit's
  `.bedrock_agentcore.yaml` shape) with the two pinned `agent_id`/`agent_arn` pairs.
- `scripts.ci.agentcore_config.render_config(*, source_path, execution_roles, output_dir,
  template_path=None) -> Path`: writes `<output_dir>/.bedrock_agentcore.yaml` and returns its
  path. `execution_roles` maps `ai_radar_curation` / `ai_radar_chat` to the role ARNs read from
  the stack outputs. It raises `ValueError` if either role ARN is missing or if the template
  lacks an `agent_id` or `agent_arn` for an agent, and it writes nothing outside `output_dir`.

Fake ARNs use a made-up account; the real account id is not needed here.

RED phase: the template and `scripts.ci.agentcore_config` do not exist yet.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from ci_synth_helpers import REPO, load  # type: ignore[import-not-found]

yaml = load("yaml")

TEMPLATE = REPO / "scripts" / "ci" / "agentcore.template.yaml"
CURATION_ID = "ai_radar_curation-FW1w976PCI"
CHAT_ID = "ai_radar_chat-JFCO0R9lkT"
ROLES = {
    "ai_radar_curation": "arn:aws:iam::111111111111:role/AiRadarRuntimeRole-Exec",
    "ai_radar_chat": "arn:aws:iam::111111111111:role/AiRadarChatRuntime-Exec",
}


@pytest.fixture
def cfg_mod():
    return load("scripts.ci.agentcore_config")


def _render(cfg_mod, tmp_path: Path, **overrides) -> dict:
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    kwargs = {
        "source_path": tmp_path / "checkout",
        "execution_roles": dict(ROLES),
        "output_dir": out,
        **overrides,
    }
    path = cfg_mod.render_config(**kwargs)
    assert path == out / ".bedrock_agentcore.yaml"
    return dict(yaml.safe_load(path.read_text()))


def test_rendered_source_path_is_the_given_checkout_path(cfg_mod, tmp_path):
    config = _render(cfg_mod, tmp_path)
    for name in ROLES:
        assert config["agents"][name]["source_path"] == str(tmp_path / "checkout")


def test_each_agent_gets_its_own_execution_role_arn(cfg_mod, tmp_path):
    config = _render(cfg_mod, tmp_path)
    for name, arn in ROLES.items():
        assert config["agents"][name]["aws"]["execution_role"] == arn


def test_rendered_agents_carry_the_existing_runtime_ids_so_deploy_updates_in_place(cfg_mod, tmp_path):
    agents = _render(cfg_mod, tmp_path)["agents"]
    assert agents["ai_radar_curation"]["bedrock_agentcore"]["agent_id"] == CURATION_ID
    assert agents["ai_radar_chat"]["bedrock_agentcore"]["agent_id"] == CHAT_ID
    assert agents["ai_radar_curation"]["bedrock_agentcore"]["agent_arn"].endswith(f"runtime/{CURATION_ID}")
    assert agents["ai_radar_chat"]["bedrock_agentcore"]["agent_arn"].endswith(f"runtime/{CHAT_ID}")


def test_rendered_config_never_lets_the_toolkit_create_a_role_or_a_repository(cfg_mod, tmp_path):
    for agent in _render(cfg_mod, tmp_path)["agents"].values():
        assert agent["aws"]["execution_role_auto_create"] is False
        assert agent["aws"]["ecr_auto_create"] is False


def test_rendered_agents_keep_their_entrypoints(cfg_mod, tmp_path):
    agents = _render(cfg_mod, tmp_path)["agents"]
    assert agents["ai_radar_curation"]["entrypoint"] == "runtime_app.py"
    assert agents["ai_radar_chat"]["entrypoint"] == "chat_app.py"


@pytest.mark.parametrize("missing", ["ai_radar_curation", "ai_radar_chat"])
def test_render_fails_when_an_execution_role_arn_is_missing(cfg_mod, tmp_path, missing):
    roles = {k: v for k, v in ROLES.items() if k != missing}
    with pytest.raises(ValueError):
        _render(cfg_mod, tmp_path, execution_roles=roles)


def test_render_fails_when_an_execution_role_arn_is_empty(cfg_mod, tmp_path):
    with pytest.raises(ValueError):
        _render(cfg_mod, tmp_path, execution_roles={**ROLES, "ai_radar_chat": ""})


@pytest.mark.parametrize("field", ["agent_id", "agent_arn"])
def test_render_fails_when_the_template_lacks_a_pinned_agent_identity(cfg_mod, tmp_path, field):
    base = yaml.safe_load(TEMPLATE.read_text())
    broken = copy.deepcopy(base)
    del broken["agents"]["ai_radar_chat"]["bedrock_agentcore"][field]
    template = tmp_path / "broken.yaml"
    template.write_text(yaml.safe_dump(broken))
    with pytest.raises(ValueError):
        _render(cfg_mod, tmp_path, template_path=template)


def test_render_writes_only_inside_the_output_directory(cfg_mod, tmp_path, monkeypatch):
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    _render(cfg_mod, tmp_path)
    assert list(elsewhere.iterdir()) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cwd", "out"]  # renderer added no sibling
    assert [p.name for p in (tmp_path / "out").iterdir()] == [".bedrock_agentcore.yaml"]


def test_render_does_not_touch_the_developers_local_config(cfg_mod, tmp_path):
    local = REPO / ".bedrock_agentcore.yaml"
    before = local.read_bytes() if local.exists() else None
    _render(cfg_mod, tmp_path)
    after = local.read_bytes() if local.exists() else None
    assert after == before

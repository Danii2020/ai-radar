"""Render the CI-only AgentCore config for `agentcore deploy` (AC6, AC12).

Reads the committed template (scripts/ci/agentcore.template.yaml), fills `source_path` with
the checkout path and each `execution_role` with the stack output ARN, and writes
`<output_dir>/.bedrock_agentcore.yaml`. It never reads or writes the developer's own
config. The template carries the two existing runtime ids, and the render fails when an id,
an ARN or a role is missing, so the toolkit can only update those runtimes.

    python -m scripts.ci.agentcore_config --output-dir "$GITHUB_WORKSPACE"
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

TEMPLATE = Path(__file__).with_name("agentcore.template.yaml")
AGENTS = ("ai_radar_curation", "ai_radar_chat")
# Stack that exports each agent's execution role (output `ExecutionRoleArn`).
ROLE_STACKS = {"ai_radar_curation": "AiRadarRuntimeRole", "ai_radar_chat": "AiRadarChatRuntime"}
_ROLE_ARN = re.compile(r"arn:aws:iam::(?P<account>[0-9]{12}):role/\S+")


def render_config(
    *,
    source_path: Path,
    execution_roles: dict[str, str],
    output_dir: Path,
    template_path: Path | None = None,
) -> Path:
    template = yaml.safe_load((template_path or TEMPLATE).read_text())
    agents = template.get("agents") or {}
    accounts: set[str] = set()
    for name in AGENTS:
        agent = agents.get(name)
        if agent is None or not hasattr(agent, "get"):
            raise ValueError(f"template has no agent {name!r}")
        identity = agent.get("bedrock_agentcore") or {}
        for field in ("agent_id", "agent_arn"):
            if not identity.get(field):
                raise ValueError(f"template agent {name!r} lacks {field}")
        arn = execution_roles.get(name, "")
        match = _ROLE_ARN.fullmatch(arn or "")
        if not match:
            raise ValueError(f"missing or malformed execution role ARN for {name!r}")
        accounts.add(match.group("account"))
    if len(accounts) != 1:
        raise ValueError("the execution roles belong to different accounts")
    account = accounts.pop()

    for name in AGENTS:
        agent = agents[name]
        agent["source_path"] = str(source_path)
        agent["aws"]["execution_role"] = execution_roles[name]
        _fill_account(agent, account)

    out = Path(output_dir) / ".bedrock_agentcore.yaml"
    out.write_text(yaml.safe_dump(template, sort_keys=False))
    return out


def _fill_account(node: Any, account: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                node[key] = value.replace("{account_id}", account)
            else:
                _fill_account(value, account)
    elif isinstance(node, list):
        node[:] = [v.replace("{account_id}", account) if isinstance(v, str) else v for v in node]
        for item in node:
            _fill_account(item, account)


def _stack_output(client: Any, stack: str, key: str) -> str:
    stacks = client.describe_stacks(StackName=stack)["Stacks"]
    for output in stacks[0].get("Outputs", []):
        if output["OutputKey"] == key:
            return str(output["OutputValue"])
    raise ValueError(f"stack {stack} has no output {key}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-path", type=Path, default=None, help="default: the current directory")
    args = parser.parse_args(argv)

    import boto3

    client = boto3.client("cloudformation", region_name="us-east-1")
    try:
        roles = {a: _stack_output(client, s, "ExecutionRoleArn") for a, s in ROLE_STACKS.items()}
        path = render_config(
            source_path=(args.source_path or Path.cwd()).resolve(),
            execution_roles=roles,
            output_dir=args.output_dir,
        )
    except ValueError as exc:
        print(f"agentcore config render failed: {exc}", file=sys.stderr)
        return 1
    print(f"rendered {path.name} for {', '.join(AGENTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

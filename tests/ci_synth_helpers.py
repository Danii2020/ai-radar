"""Shared helpers for the backend-cicd-pipeline tests (specs/backend-cicd-pipeline).

Not a test module. Provides:

- `load(name)`: import a module by dotted name at call time, so a not-yet-written
  implementation module fails the test with `ModuleNotFoundError` (the red reason)
  instead of breaking collection or the type checker. The repo root and `infra/` are
  put on `sys.path` (CI helpers live in `scripts/ci/`, the CI access app in
  `infra/ci_bootstrap/`).
- `read_pinned_context()`: the committed deploy context file (`scripts/ci/deploy_context.json`).
- `synth_backend_templates()`: the seven backend stacks synthesized once per session with
  the pinned context, into a throw-away output directory.
- `flatten()`/`norm()`: turn CloudFormation intrinsics into comparable strings. The account
  id (any 12 digits or the `AWS::AccountId` pseudo parameter) becomes `ACCT` and the region
  becomes `REGION`, so no test pins the account literal.
- `synth_ci_access()`: the CI access stack (`infra/ci_bootstrap/ci_access_stack.py`).
"""
from __future__ import annotations

import atexit
import functools
import importlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).parent.parent
INFRA = REPO / "infra"
for _p in (str(REPO), str(INFRA)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CONTEXT_FILE = REPO / "scripts" / "ci" / "deploy_context.json"
FAKE_CHAT_API_ID = "fakeapi123"

STACK_NAMES = [
    "AiRadarCardStore",
    "AiRadarRuntimeRole",
    "AiRadarSchedule",
    "AiRadarBudget",
    "AiRadarFeedApi",
    "AiRadarChatRuntime",
    "AiRadarChatApi",
]


def load(name: str) -> Any:
    return importlib.import_module(name)


def read_pinned_context() -> dict[str, str]:
    return dict(json.loads(CONTEXT_FILE.read_text()))


def _outdir() -> str:
    path = tempfile.mkdtemp(prefix="ci-synth-")
    atexit.register(shutil.rmtree, path, ignore_errors=True)
    return path


def synth_stack(name: str, context: dict[str, str]) -> dict[str, Any]:
    """Synthesize one backend stack with the given CDK context; return its template JSON."""
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    classes = {
        "AiRadarCardStore": ("stacks.card_store_stack", "CardStoreStack"),
        "AiRadarRuntimeRole": ("stacks.agent_runtime_stack", "AgentRuntimeStack"),
        "AiRadarSchedule": ("stacks.curation_schedule_stack", "CurationScheduleStack"),
        "AiRadarBudget": ("stacks.cost_budget_stack", "CostBudgetStack"),
        "AiRadarFeedApi": ("stacks.feed_api_stack", "FeedApiStack"),
        "AiRadarChatRuntime": ("stacks.chat_runtime_stack", "ChatRuntimeStack"),
        "AiRadarChatApi": ("stacks.chat_api_stack", "ChatApiStack"),
    }
    module, cls = classes[name]
    app = cdk.App(context=context, outdir=_outdir())
    stack = getattr(importlib.import_module(module), cls)(app, name)
    return dict(Template.from_stack(stack).to_json())


@functools.cache
def synth_backend_templates() -> dict[str, dict[str, Any]]:
    """All seven backend stacks synthesized with the committed pinned context."""
    context = read_pinned_context()
    return {name: synth_stack(name, context) for name in STACK_NAMES}


def synth_ci_access(context: dict[str, str] | None = None) -> dict[str, Any]:
    """Synthesize the CI access stack with a fake chat API id (never a real one)."""
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    ctx = {"chat_api_id": FAKE_CHAT_API_ID} if context is None else context
    module = importlib.import_module("ci_bootstrap.ci_access_stack")
    app = cdk.App(context=ctx, outdir=_outdir())
    stack = module.CiAccessStack(app, "TestCiAccess")
    return dict(Template.from_stack(stack).to_json())


@functools.cache
def ci_access_template() -> dict[str, Any]:
    return synth_ci_access()


# --- intrinsic flattening -------------------------------------------------------------


def flatten(value: Any) -> str:
    """Render a template value (string, Fn::Join, Ref, ...) as one comparable string."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "Fn::Join" in value:
            sep, parts = value["Fn::Join"]
            return str(sep).join(flatten(p) for p in parts)
        if "Fn::Sub" in value:
            sub = value["Fn::Sub"]
            return flatten(sub[0] if isinstance(sub, list) else sub)
        if "Ref" in value:
            ref = value["Ref"]
            return {
                "AWS::AccountId": "ACCT",
                "AWS::Region": "REGION",
                "AWS::Partition": "aws",
            }.get(ref, "{Ref:" + ref + "}")
        if "Fn::GetAtt" in value:
            return "{GetAtt:" + ".".join(value["Fn::GetAtt"]) + "}"
    return json.dumps(value, sort_keys=True)


def norm(value: Any) -> str:
    """`flatten`, then replace literal account ids and the region with placeholders."""
    text = flatten(value)
    text = re.sub(r"(?<![0-9])[0-9]{12}(?![0-9])", "ACCT", text)
    return text.replace("us-east-1", "REGION")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def resources_of(template: dict[str, Any], *types: str) -> dict[str, dict[str, Any]]:
    return {k: r for k, r in template["Resources"].items() if r["Type"] in types}

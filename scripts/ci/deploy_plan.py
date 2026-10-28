"""Deploy planner: which targets a push to `main` must deploy (AC4, AC5).

Pure functions plus a thin CLI. The base of the diff is the head commit of the last
SUCCESSFUL deploy run (never the push's parent), so a run that replaces a queued one still
deploys every change since the last success. With no base, or a base that is not an
ancestor of HEAD, every target is selected. An unmapped path under a deploy-relevant root
also selects everything (fail-safe); CDK skips unchanged stacks, so over-selecting only
costs time.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable

# Dependency order: roles before agents, the schedule reads the curation agent's ARN from
# SSM, the chat API points at the chat runtime. There are no cross-stack exports, so CDK
# would not infer this order.
TARGET_ORDER: list[str] = [
    "AiRadarCardStore",
    "AiRadarRuntimeRole",
    "AiRadarChatRuntime",
    "ai_radar_curation",
    "ai_radar_chat",
    "AiRadarSchedule",
    "AiRadarBudget",
    "AiRadarFeedApi",
    "AiRadarChatApi",
]
STACKS = [t for t in TARGET_ORDER if t.startswith("AiRadar")]
AGENTS = ["ai_radar_curation", "ai_radar_chat"]
APIS = ["AiRadarFeedApi", "AiRadarChatApi"]
ALL = set(TARGET_ORDER)

# File -> targets for infra construct and stack modules.
_INFRA_FILES: dict[str, set[str]] = {
    "infra/lib/card_store.py": {"AiRadarCardStore"},
    "infra/stacks/card_store_stack.py": {"AiRadarCardStore"},
    "infra/lib/agent_runtime.py": {"AiRadarRuntimeRole"},
    "infra/stacks/agent_runtime_stack.py": {"AiRadarRuntimeRole"},
    "infra/lib/chat_runtime.py": {"AiRadarChatRuntime"},
    "infra/stacks/chat_runtime_stack.py": {"AiRadarChatRuntime"},
    "infra/lib/curation_schedule.py": {"AiRadarSchedule"},
    "infra/stacks/curation_schedule_stack.py": {"AiRadarSchedule"},
    "infra/lib/cost_budget.py": {"AiRadarBudget"},
    "infra/stacks/cost_budget_stack.py": {"AiRadarBudget"},
    "infra/lib/feed_api.py": {"AiRadarFeedApi"},
    "infra/stacks/feed_api_stack.py": {"AiRadarFeedApi"},
    "infra/lib/chat_api.py": {"AiRadarChatApi"},
    "infra/stacks/chat_api_stack.py": {"AiRadarChatApi"},
}
_ROOT_FILES: dict[str, set[str]] = {
    "Dockerfile.feed_api": {"AiRadarFeedApi"},
    "Dockerfile.chat_api": {"AiRadarChatApi"},
    "Dockerfile": set(AGENTS),
    "runtime_app.py": set(AGENTS),
    "chat_app.py": set(AGENTS),
    "pyproject.toml": set(AGENTS) | set(APIS),
    "uv.lock": set(AGENTS) | set(APIS),
    ".dockerignore": set(AGENTS) | set(APIS),
}
# Applied by the humans, never deployed by CI.
_HUMAN_APPLIED_PREFIXES = ("infra/ci_bootstrap/",)
_HUMAN_APPLIED_FILES = {"scripts/ci/repo_protection.py", ".github/CODEOWNERS"}


def targets_for_path(path: str) -> set[str]:
    """The targets one changed path selects (empty set: nothing to deploy)."""
    if path in _HUMAN_APPLIED_FILES or path.startswith(_HUMAN_APPLIED_PREFIXES):
        return set()
    if path in _ROOT_FILES:
        return set(_ROOT_FILES[path])
    if path in _INFRA_FILES:
        return set(_INFRA_FILES[path])
    # The pipeline itself (workflows, helpers, context file, agent config template).
    if path.startswith((".github/workflows/backend-", "scripts/")):
        return set(ALL)
    if path.startswith("infra/"):
        # infra/app.py, infra/cdk.json, lib/__init__.py and any unmapped file.
        return set(STACKS)
    if path.startswith("src/chat_api/"):
        return {"AiRadarChatApi"}
    if path.startswith(("src/api/", "src/contracts/")):
        return {"AiRadarFeedApi"}
    if path.startswith("src/"):
        return set(AGENTS)  # one shared image (RD-8)
    return set()


def plan_targets(changed_paths: Iterable[str]) -> list[str]:
    selected: set[str] = set()
    for path in changed_paths:
        selected |= targets_for_path(path)
    return [t for t in TARGET_ORDER if t in selected]


def compute_plan(
    *,
    head: str,
    last_success_sha: str | None,
    is_ancestor: Callable[[str, str], bool],
    changed_paths_since: Callable[[str], list[str]],
) -> list[str]:
    if not last_success_sha or not is_ancestor(last_success_sha, head):
        return list(TARGET_ORDER)
    return plan_targets(changed_paths_since(last_success_sha))


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def _is_ancestor(base: str, head: str) -> bool:
    return _git("merge-base", "--is-ancestor", base, head).returncode == 0


def _changed_paths_since(base: str) -> list[str]:
    result = _git("diff", "--name-only", base, "HEAD")
    if result.returncode != 0:
        raise RuntimeError("git diff failed")
    return [line for line in result.stdout.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute the deploy targets for HEAD.")
    parser.add_argument("--last-success", default="", help="head sha of the last successful deploy run")
    parser.add_argument("--all", action="store_true", help="select every target (manual re-run)")
    args = parser.parse_args(argv)

    head = _git("rev-parse", "HEAD").stdout.strip()
    if args.all:
        targets = list(TARGET_ORDER)
    else:
        try:
            targets = compute_plan(
                head=head,
                last_success_sha=args.last_success or None,
                is_ancestor=_is_ancestor,
                changed_paths_since=_changed_paths_since,
            )
        except RuntimeError:
            targets = list(TARGET_ORDER)  # fail safe

    print(f"deploy targets: {', '.join(targets) if targets else 'none'}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"targets={json.dumps(targets)}\n")
            fh.write(f"has_targets={'true' if targets else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

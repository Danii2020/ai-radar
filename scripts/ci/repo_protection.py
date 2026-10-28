"""Repository protection for `Danii2020/ai-radar` (AC14). Run by a human only.

    uv run python -m scripts.ci.repo_protection            # dry run: GETs only, prints the changes
    uv run python -m scripts.ci.repo_protection --apply    # writes only what differs from the read state

Needs the `gh` CLI authenticated as a repository admin. Re-running changes nothing once the
settings match. Each payload is built by a pure function; every call goes through one
injectable runner `gh(method, endpoint, body=None) -> parsed JSON`.

Sets: a ruleset on `main` (pull request required, the AC1 check jobs required and the branch
up to date, no force push, no deletion, no bypass actors); secret scanning and push
protection; a read-only default workflow token that cannot approve PRs; approval before
workflows run for every outside contributor's PR. Required approvals stay 0 and code-owner
review stays off while there is one maintainer (GitHub does not let an author approve their
own PR); raise both when a second maintainer joins.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

OWNER = "Danii2020"
NAME = "ai-radar"
REPO = f"/repos/{OWNER}/{NAME}"
RULESET_NAME = "main-protection"

# `<caller job> / <called job>` as named in .github/workflows/backend-pr.yml and
# backend-checks.yml; tests/test_ci_workflows.py keeps this list equal to the workflow.
REQUIRED_CHECKS: list[str] = ["checks / pytest", "checks / lint", "checks / synth"]

GH = Callable[[str, str, dict[str, Any] | None], Any]


def ruleset_payload() -> dict[str, Any]:
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "bypass_actors": [],
        "rules": [
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": False,
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [{"context": c} for c in REQUIRED_CHECKS],
                },
            },
            {"type": "non_fast_forward"},
            {"type": "deletion"},
        ],
    }


def security_payload() -> dict[str, Any]:
    return {
        "security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
        }
    }


def workflow_permissions_payload() -> dict[str, Any]:
    return {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False}


def fork_approval_payload() -> dict[str, Any]:
    return {"approval_policy": "all_external_contributors"}


def _subset(desired: Any, current: Any) -> bool:
    """True when `current` already has everything `desired` asks for (extra server fields ignored)."""
    if isinstance(desired, dict):
        return isinstance(current, dict) and all(k in current and _subset(v, current[k]) for k, v in desired.items())
    if isinstance(desired, list):
        return (
            isinstance(current, list)
            and len(desired) == len(current)
            and all(_subset(d, c) for d, c in zip(desired, current, strict=True))
        )
    return bool(desired == current)


def _normalized_ruleset(ruleset: dict[str, Any]) -> dict[str, Any]:
    out = dict(ruleset)
    out["rules"] = sorted(ruleset.get("rules", []), key=lambda r: str(r.get("type")))
    return out


def plan_changes(gh: GH) -> list[tuple[str, str, dict[str, Any]]]:
    """Read the current state (GETs only) and return `(method, endpoint, body)` for what differs."""
    changes: list[tuple[str, str, dict[str, Any]]] = []

    desired = ruleset_payload()
    existing = next((r for r in gh("GET", f"{REPO}/rulesets", None) or [] if r.get("name") == RULESET_NAME), None)
    if existing is None:
        changes.append(("POST", f"{REPO}/rulesets", desired))
    else:
        current = gh("GET", f"{REPO}/rulesets/{existing['id']}", None)
        if not _subset(_normalized_ruleset(desired), _normalized_ruleset(current)):
            changes.append(("PUT", f"{REPO}/rulesets/{existing['id']}", desired))

    security = security_payload()
    if not _subset(security, gh("GET", REPO, None)):
        changes.append(("PATCH", REPO, security))

    for endpoint, payload in (
        (f"{REPO}/actions/permissions/workflow", workflow_permissions_payload()),
        (f"{REPO}/actions/permissions/fork-pr-contributor-approval", fork_approval_payload()),
    ):
        if not _subset(payload, gh("GET", endpoint, None)):
            changes.append(("PUT", endpoint, payload))
    return changes


def _gh_cli(method: str, endpoint: str, body: dict[str, Any] | None = None) -> Any:
    command = ["gh", "api", "-X", method, endpoint]
    stdin = None
    if body is not None:
        command += ["--input", "-"]
        stdin = json.dumps(body)
    result = subprocess.run(command, input=stdin, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh api {method} {endpoint} failed: {result.stderr.strip()}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def main(argv: list[str], gh: GH | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: print only)")
    args = parser.parse_args(argv)
    runner: GH = gh if gh is not None else _gh_cli

    changes = plan_changes(runner)
    if not changes:
        print("repository protection already matches; nothing to change")
        return 0
    for method, endpoint, body in changes:
        print(f"{'APPLY' if args.apply else 'WOULD'} {method} {endpoint}")
        print(json.dumps(body, indent=2, sort_keys=True))
    if not args.apply:
        print("dry run: no write call made; re-run with --apply to write")
        return 0
    for method, endpoint, body in changes:
        runner(method, endpoint, body)
    print("applied; verify with: gh api repos/Danii2020/ai-radar/rulesets and gh api repos/Danii2020/ai-radar")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

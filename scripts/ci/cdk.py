"""The only way CI runs `cdk`: the caller's arguments plus the pinned context (AC6).

    python -m scripts.ci.cdk deploy --exclusively AiRadarBudget --require-approval never

Refuses any caller-supplied `-c` / `--context`, so no run can pass a `schedule_*` key or a
different CORS origin than the committed file.
"""
from __future__ import annotations

import subprocess
import sys

from scripts.ci.deploy_context import context_args, load_context

APP = "python infra/app.py"


def cdk_argv(args: list[str], context: dict[str, str] | None = None) -> list[str]:
    for arg in args:
        if arg in ("-c", "--context") or arg.startswith(("--context=", "-c=")):
            raise ValueError("pass context only through scripts/ci/deploy_context.json")
    pinned = load_context() if context is None else context
    return ["cdk", "--app", APP, *args, *context_args(pinned)]


def main(argv: list[str] | None = None) -> int:
    try:
        command = cdk_argv(list(sys.argv[1:] if argv is None else argv))
    except ValueError as exc:
        print(f"cdk wrapper: {exc}", file=sys.stderr)
        return 2
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

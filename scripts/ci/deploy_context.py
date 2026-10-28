"""The pinned CDK deploy context and the origin validation (AC6, AC15).

`deploy_context.json` is the one committed source of `-c key=value` flags for every CI
`cdk synth`, `diff` and `deploy`, and the one place a human changes them (by PR). It never
carries a `schedule_*` key. Run as `python -m scripts.ci.deploy_context` to validate it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CONTEXT_FILE = Path(__file__).with_name("deploy_context.json")
ORIGINS_KEY = "feed_api_allowed_origins"

_LOCALHOST = re.compile(r"http://localhost:[0-9]{1,5}")
_HTTPS = re.compile(r"https://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:[0-9]{1,5})?")
_PLACEHOLDER_CHARS = "<>{}"


def validate_origins(value: str) -> None:
    """Raise `ValueError` unless every comma-separated origin is safe to deploy.

    Accepted: `http://localhost:<port>` or an `https://<host>[:port]` origin with no path.
    Rejected: empty values or members, placeholder-shaped text, other plain-http origins.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("feed_api_allowed_origins is empty")
    for raw in value.split(","):
        origin = raw.strip()
        if not origin:
            raise ValueError("feed_api_allowed_origins has an empty member")
        if any(c in origin for c in _PLACEHOLDER_CHARS) or "placeholder" in origin.lower():
            raise ValueError(f"origin looks like a placeholder: {origin!r}")
        if not (_LOCALHOST.fullmatch(origin) or _HTTPS.fullmatch(origin)):
            raise ValueError(
                f"origin must be http://localhost:<port> or an https:// origin without a path: {origin!r}"
            )


def load_context(path: Path | None = None) -> dict[str, str]:
    """Read the committed context file; validate the origins when present."""
    raw = json.loads((path or CONTEXT_FILE).read_text())
    context = {str(k): str(v) for k, v in raw.items()}
    if ORIGINS_KEY in context:
        validate_origins(context[ORIGINS_KEY])
    return context


def context_args(context: dict[str, str]) -> list[str]:
    """`["-c", "k=v", ...]` for the `cdk` command line, in key order."""
    args: list[str] = []
    for key in sorted(context):
        args += ["-c", f"{key}={context[key]}"]
    return args


def main() -> int:
    try:
        context = load_context()
        bad = [k for k in context if k.startswith("schedule_")]
        if bad:
            raise ValueError(f"the deploy context must not carry schedule keys: {bad}")
    except (ValueError, OSError) as exc:
        print(f"deploy context invalid: {exc}", file=sys.stderr)
        return 1
    print(f"deploy context ok ({len(context)} keys)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

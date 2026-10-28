"""Fail the run unless the synthesized curation schedule is `DISABLED` (SC-1, AC6).

    python -m scripts.ci.schedule_guard cdk.out
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TEMPLATE_NAME = "AiRadarSchedule.template.json"
SCHEDULE_TYPE = "AWS::Scheduler::Schedule"


class ScheduleGuardError(Exception):
    """The schedule is missing or not DISABLED."""


def check_template(template: dict[str, Any]) -> None:
    schedules = [r for r in template.get("Resources", {}).values() if r.get("Type") == SCHEDULE_TYPE]
    if len(schedules) != 1:
        raise ScheduleGuardError(f"expected exactly one {SCHEDULE_TYPE}, found {len(schedules)}")
    state = schedules[0].get("Properties", {}).get("State")
    if state != "DISABLED":
        # An absent State means ENABLED to EventBridge Scheduler, so it fails too.
        raise ScheduleGuardError(f"schedule State is {state!r}, expected 'DISABLED'")


def check_cdk_out(cdk_out: Path) -> None:
    path = Path(cdk_out) / TEMPLATE_NAME
    if not path.is_file():
        raise ScheduleGuardError(f"{TEMPLATE_NAME} not found in {cdk_out}")
    check_template(json.loads(path.read_text()))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        check_cdk_out(Path(args[0] if args else "cdk.out"))
    except ScheduleGuardError as exc:
        print(f"schedule guard failed: {exc}", file=sys.stderr)
        return 1
    print("schedule guard ok: AiRadarSchedule is DISABLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

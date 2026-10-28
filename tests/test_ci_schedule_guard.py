"""Schedule guard over the synthesized `AiRadarSchedule` template
(spec backend-cicd-pipeline, outcome O1; AC6).

Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation row AC6 (schedule guard).

Interface (names chosen by the test writer):
- `scripts.ci.schedule_guard.ScheduleGuardError` (an `Exception`).
- `scripts.ci.schedule_guard.check_template(template: dict) -> None`: passes only when the
  template has exactly one `AWS::Scheduler::Schedule` and its `State` is `DISABLED`.
- `scripts.ci.schedule_guard.check_cdk_out(cdk_out: Path) -> None`: reads
  `AiRadarSchedule.template.json` from a `cdk synth` output directory and applies the check;
  a missing template is also an error.

RED phase: `scripts.ci.schedule_guard` does not exist yet.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from ci_synth_helpers import (  # type: ignore[import-not-found]
    load,
    read_pinned_context,
    synth_stack,
)


@pytest.fixture(scope="module")
def real_template() -> dict:
    return synth_stack("AiRadarSchedule", read_pinned_context())


@pytest.fixture
def guard():
    return load("scripts.ci.schedule_guard")


def _schedule(template: dict) -> dict:
    return next(r for r in template["Resources"].values() if r["Type"] == "AWS::Scheduler::Schedule")


def test_guard_passes_on_the_real_synthesized_template(guard, real_template):
    guard.check_template(real_template)


def test_guard_fails_when_the_schedule_state_is_enabled(guard, real_template):
    mutated = copy.deepcopy(real_template)
    _schedule(mutated)["Properties"]["State"] = "ENABLED"
    with pytest.raises(guard.ScheduleGuardError):
        guard.check_template(mutated)


def test_guard_fails_when_the_state_is_missing(guard, real_template):
    # Scheduler defaults an absent State to ENABLED, so absence is not "disabled".
    mutated = copy.deepcopy(real_template)
    del _schedule(mutated)["Properties"]["State"]
    with pytest.raises(guard.ScheduleGuardError):
        guard.check_template(mutated)


def test_guard_fails_when_the_template_has_no_schedule(guard, real_template):
    mutated = copy.deepcopy(real_template)
    mutated["Resources"] = {
        k: r for k, r in mutated["Resources"].items() if r["Type"] != "AWS::Scheduler::Schedule"
    }
    with pytest.raises(guard.ScheduleGuardError):
        guard.check_template(mutated)


def test_guard_reads_the_template_from_a_cdk_out_directory(guard, real_template, tmp_path: Path):
    (tmp_path / "AiRadarSchedule.template.json").write_text(json.dumps(real_template))
    guard.check_cdk_out(tmp_path)

    enabled = copy.deepcopy(real_template)
    _schedule(enabled)["Properties"]["State"] = "ENABLED"
    (tmp_path / "AiRadarSchedule.template.json").write_text(json.dumps(enabled))
    with pytest.raises(guard.ScheduleGuardError):
        guard.check_cdk_out(tmp_path)


def test_guard_fails_when_the_schedule_template_is_absent(guard, tmp_path: Path):
    with pytest.raises(guard.ScheduleGuardError):
        guard.check_cdk_out(tmp_path)

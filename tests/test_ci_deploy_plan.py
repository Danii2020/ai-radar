"""Deploy planner: base commit, path-to-target mapping and ordering
(spec backend-cicd-pipeline, outcome O2; AC4, AC5).

Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation rows AC4 and AC5, and
"Decision (change detection)" / "Decision (dependency order)".

Interface (names chosen by the test writer):
- `scripts.ci.deploy_plan.TARGET_ORDER: list[str]`: the nine targets in dependency order.
  Stacks keep their CloudFormation names; the agents are `ai_radar_curation` and
  `ai_radar_chat`.
- `plan_targets(changed_paths: Iterable[str]) -> list[str]`: pure; ordered, deduplicated.
- `compute_plan(*, head, last_success_sha, is_ancestor, changed_paths_since) -> list[str]`:
  `last_success_sha` is the head sha of the last successful deploy run (or None);
  `is_ancestor(base, head) -> bool` and `changed_paths_since(base) -> list[str]` are the
  injected git seams. No base, or a base that is not an ancestor of `head`, selects every
  target (and need not call `changed_paths_since`).

RED phase: `scripts.ci.deploy_plan` does not exist yet.
"""
from __future__ import annotations

import pytest
from ci_synth_helpers import REPO, STACK_NAMES, load  # type: ignore[import-not-found]

ORDER = [
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
AGENTS = ["ai_radar_curation", "ai_radar_chat"]


@pytest.fixture
def plan():
    return load("scripts.ci.deploy_plan")


def _ordered(targets: set[str]) -> list[str]:
    return [t for t in ORDER if t in targets]


# --- ordering and the fail-safe shape (AC5) ---------------------------------------------------


def test_target_order_is_the_pinned_dependency_order(plan):
    assert list(plan.TARGET_ORDER) == ORDER


def test_plan_output_follows_dependency_order_regardless_of_input_order(plan):
    got = plan.plan_targets(["src/chat_api/handler.py", "infra/lib/card_store.py", "infra/lib/cost_budget.py"])
    assert got == ["AiRadarCardStore", "AiRadarBudget", "AiRadarChatApi"]


def test_plan_has_no_duplicates_when_several_paths_select_the_same_target(plan):
    got = plan.plan_targets(["src/chat_api/handler.py", "src/chat_api/config.py", "Dockerfile.chat_api"])
    assert got == ["AiRadarChatApi"]


# --- mapping table (AC5) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        # nothing deploy-relevant
        (["README.md"], set()),
        (["apps/web/src/app/page.tsx", "apps/web/package.json"], set()),
        (["docs/design.md", "specs/x/intent.md", "tests/test_x.py"], set()),
        (["run_chat.py"], set()),  # other root scripts
        ([], set()),
        # one stack only
        (["src/chat_api/handler.py"], {"AiRadarChatApi"}),
        (["Dockerfile.chat_api"], {"AiRadarChatApi"}),
        (["infra/lib/chat_api.py"], {"AiRadarChatApi"}),
        (["infra/stacks/chat_api_stack.py"], {"AiRadarChatApi"}),
        (["Dockerfile.feed_api"], {"AiRadarFeedApi"}),
        (["infra/lib/cost_budget.py"], {"AiRadarBudget"}),
        (["infra/lib/curation_schedule.py"], {"AiRadarSchedule"}),
        (["infra/lib/card_store.py"], {"AiRadarCardStore"}),
        (["infra/lib/agent_runtime.py"], {"AiRadarRuntimeRole"}),
        (["infra/lib/chat_runtime.py"], {"AiRadarChatRuntime"}),
        # agents only (one shared image, no stack)
        (["src/chat/graph.py"], set(AGENTS)),
        (["runtime_app.py"], set(AGENTS)),
        (["chat_app.py"], set(AGENTS)),
        (["Dockerfile"], set(AGENTS)),
        # dependencies change the images and the two Lambda images
        (["uv.lock"], set(AGENTS) | {"AiRadarFeedApi", "AiRadarChatApi"}),
        (["pyproject.toml"], set(AGENTS) | {"AiRadarFeedApi", "AiRadarChatApi"}),
        # the whole infra app
        (["infra/app.py"], set(STACK_NAMES)),
        (["infra/cdk.json"], set(STACK_NAMES)),
        # humans apply these; CI never deploys them
        (["infra/ci_bootstrap/ci_access_stack.py"], set()),
        ([".github/CODEOWNERS"], set()),
        (["scripts/ci/repo_protection.py"], set()),
    ],
)
def test_changed_paths_select_the_expected_targets(plan, paths, expected):
    got = plan.plan_targets(paths)
    assert set(got) == expected
    assert got == _ordered(expected)


def test_feed_api_sources_select_the_feed_api_and_not_the_chat_api(plan):
    got = plan.plan_targets(["src/api/handler.py"])
    assert "AiRadarFeedApi" in got
    assert "AiRadarChatApi" not in got


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/backend-deploy.yml",
        ".github/workflows/backend-checks.yml",
        "scripts/ci/deploy_plan.py",
        "scripts/ci/agentcore_config.py",
    ],
)
def test_a_change_to_the_pipeline_itself_selects_every_target(plan, path):
    assert plan.plan_targets([path]) == ORDER


@pytest.mark.parametrize("path", ["infra/brand_new_helper.py", "infra/lib/brand_new_construct.py"])
def test_an_unmapped_path_under_infra_selects_the_whole_infra_app(plan, path):
    assert set(STACK_NAMES) <= set(plan.plan_targets([path]))


def test_every_construct_and_stack_file_maps_to_at_least_one_stack(plan):
    files = sorted(
        p.relative_to(REPO).as_posix()
        for d in ("infra/lib", "infra/stacks")
        for p in (REPO / d).glob("*.py")
    )
    assert files
    for f in files:
        assert set(plan.plan_targets([f])) & set(STACK_NAMES), f


def test_irrelevant_paths_alongside_a_relevant_one_do_not_add_targets(plan):
    assert plan.plan_targets(["README.md", "src/chat_api/handler.py"]) == ["AiRadarChatApi"]


# --- base commit and superseded runs (AC4) -------------------------------------------------------


def _seams(*, ancestors: set[tuple[str, str]], changed: dict[str, list[str]]):
    calls: list[str] = []

    def is_ancestor(base: str, head: str) -> bool:
        return (base, head) in ancestors

    def changed_paths_since(base: str) -> list[str]:
        calls.append(base)
        return changed[base]

    return is_ancestor, changed_paths_since, calls


def test_base_case_plan_covers_every_change_since_the_last_successful_deploy(plan):
    # A deployed; B (budget) was superseded in the queue; C (chat api) is the run that executes.
    is_ancestor, since, calls = _seams(
        ancestors={("A", "C")},
        changed={"A": ["infra/lib/cost_budget.py", "src/chat_api/handler.py"]},
    )
    got = plan.compute_plan(head="C", last_success_sha="A", is_ancestor=is_ancestor, changed_paths_since=since)
    assert got == ["AiRadarBudget", "AiRadarChatApi"]
    assert calls == ["A"]  # diffed against the last success, not against C's parent


def test_base_case_failed_previous_run_changes_are_retried_by_the_next_run(plan):
    # B failed, so the last success is still A and B's change is part of C's plan.
    is_ancestor, since, _ = _seams(
        ancestors={("A", "C")},
        changed={"A": ["infra/lib/feed_api.py", "README.md"]},
    )
    got = plan.compute_plan(head="C", last_success_sha="A", is_ancestor=is_ancestor, changed_paths_since=since)
    assert got == ["AiRadarFeedApi"]


def test_base_case_nothing_deploy_relevant_since_the_last_success_gives_an_empty_plan(plan):
    is_ancestor, since, _ = _seams(ancestors={("A", "B")}, changed={"A": ["README.md", "apps/web/x.ts"]})
    assert plan.compute_plan(head="B", last_success_sha="A", is_ancestor=is_ancestor, changed_paths_since=since) == []


def test_base_case_no_previous_successful_deploy_selects_every_target(plan):
    is_ancestor, since, _ = _seams(ancestors=set(), changed={})
    got = plan.compute_plan(head="C", last_success_sha=None, is_ancestor=is_ancestor, changed_paths_since=since)
    assert got == ORDER


def test_base_case_previous_commit_that_is_not_an_ancestor_selects_every_target(plan):
    # e.g. history was rewritten, or the sha is unknown to this checkout
    is_ancestor, since, _ = _seams(ancestors=set(), changed={"A": ["README.md"]})
    got = plan.compute_plan(head="C", last_success_sha="A", is_ancestor=is_ancestor, changed_paths_since=since)
    assert got == ORDER


def test_base_case_head_equal_to_the_last_success_is_a_plain_ancestor_with_no_changes(plan):
    is_ancestor, since, _ = _seams(ancestors={("A", "A")}, changed={"A": []})
    assert plan.compute_plan(head="A", last_success_sha="A", is_ancestor=is_ancestor, changed_paths_since=since) == []


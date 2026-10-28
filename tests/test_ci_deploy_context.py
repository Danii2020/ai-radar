"""Pinned CDK deploy context, origin validation and the `cdk` wrapper
(spec backend-cicd-pipeline, outcome O1; AC6, AC15).

Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation rows AC6 (context file
and wrapper) and AC15 (origin validation, CORS equals the file).

Interfaces the implementation must provide (names chosen by the test writer, the plan
only suggests `scripts/ci/`):
- `scripts/ci/deploy_context.json`: the one committed context file, a flat JSON object.
- `scripts.ci.deploy_context.load_context(path=None) -> dict[str, str]` (default: the file).
- `scripts.ci.deploy_context.validate_origins(value: str) -> None`: raises `ValueError`.
- `scripts.ci.deploy_context.context_args(context) -> list[str]`: `["-c", "k=v", ...]`.
- `scripts.ci.cdk.cdk_argv(args, context=None) -> list[str]`: the `cdk` command line the
  wrapper runs: the caller's args plus the pinned `-c` flags; it refuses any `-c` /
  `--context` supplied by the caller.

RED phase: none of these exist yet.
"""
from __future__ import annotations

import pytest
from ci_synth_helpers import (  # type: ignore[import-not-found]
    load,
    read_pinned_context,
    synth_stack,
)

EXPECTED_KEYS = {
    "feed_api_reserved_concurrency",
    "chat_api_reserved_concurrency",
    "budget_limit_usd",
    "feed_api_allowed_origins",
}


@pytest.fixture
def ctx_mod():
    return load("scripts.ci.deploy_context")


# --- the committed file (AC6) -----------------------------------------------------------


def test_context_file_holds_exactly_the_four_pinned_keys():
    assert set(read_pinned_context()) == EXPECTED_KEYS


def test_context_file_keeps_the_lambda_quota_workaround_and_the_budget_limit():
    # Without these a CI deploy would fail on the account's Lambda quota (10) or change the budget.
    ctx = read_pinned_context()
    assert ctx["feed_api_reserved_concurrency"] == "none"
    assert ctx["chat_api_reserved_concurrency"] == "none"
    assert str(ctx["budget_limit_usd"]) == "500"


def test_context_file_carries_no_schedule_key():
    assert [k for k in read_pinned_context() if k.startswith("schedule_")] == []


def test_load_context_returns_the_committed_file(ctx_mod):
    assert ctx_mod.load_context() == read_pinned_context()


def test_committed_origins_pass_the_validation(ctx_mod):
    ctx_mod.validate_origins(read_pinned_context()["feed_api_allowed_origins"])


# --- origin validation (AC15) -----------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:3000",
        "https://ai-radar-xyz.vercel.app",
        "http://localhost:3000,https://ai-radar-xyz.vercel.app",
        "http://localhost:3000, https://ai-radar-xyz.vercel.app",
    ],
)
def test_origin_validation_accepts_localhost_and_https_origins(ctx_mod, value):
    ctx_mod.validate_origins(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://<project>.vercel.app",  # placeholder-shaped
        "https://{project}.vercel.app",
        "https://placeholder.vercel.app",
        "http://example.com",  # plain http that is not localhost
        "https://ai-radar-xyz.vercel.app/app",  # has a path
        "http://localhost",  # localhost needs a port
        "",  # empty
        "   ",
        "http://localhost:3000,https://<project>.vercel.app",  # one bad origin spoils the list
        "http://localhost:3000,",  # empty member
    ],
)
def test_origin_validation_rejects_unsafe_or_placeholder_values(ctx_mod, value):
    with pytest.raises(ValueError):
        ctx_mod.validate_origins(value)


# --- context args and the wrapper (AC6) --------------------------------------------------


def test_context_args_emit_one_dash_c_pair_per_key(ctx_mod):
    args = ctx_mod.context_args({"budget_limit_usd": "500", "feed_api_reserved_concurrency": "none"})
    pairs = [args[i + 1] for i, a in enumerate(args) if a == "-c"]
    assert sorted(pairs) == ["budget_limit_usd=500", "feed_api_reserved_concurrency=none"]
    assert args.count("-c") == len(args) // 2  # nothing but -c pairs


def test_wrapper_passes_exactly_the_pinned_context_on_every_command():
    cdk = load("scripts.ci.cdk")
    pinned = read_pinned_context()
    for sub in (["synth"], ["diff", "--method=template"], ["deploy", "--exclusively", "AiRadarBudget"]):
        argv = cdk.cdk_argv(sub)
        flagged = {argv[i + 1] for i, a in enumerate(argv) if a == "-c"}
        assert flagged == {f"{k}={v}" for k, v in pinned.items()}
        assert argv[argv.index(sub[0])] == sub[0]
        assert not any(a.startswith("schedule_") or "schedule_" in a for a in argv)


def test_wrapper_keeps_the_callers_arguments_in_order():
    cdk = load("scripts.ci.cdk")
    argv = cdk.cdk_argv(["deploy", "--exclusively", "AiRadarBudget", "--require-approval", "never"])
    start = argv.index("deploy")
    assert argv[start : start + 5] == [
        "deploy",
        "--exclusively",
        "AiRadarBudget",
        "--require-approval",
        "never",
    ]


@pytest.mark.parametrize(
    "extra",
    [
        ["-c", "schedule_enabled=true"],
        ["--context", "schedule_expression=rate(1 minute)"],
        ["-c", "feed_api_allowed_origins=https://other.example.app"],
    ],
)
def test_wrapper_refuses_context_supplied_by_the_caller(extra):
    cdk = load("scripts.ci.cdk")
    with pytest.raises(ValueError):
        cdk.cdk_argv(["deploy", *extra])


# --- the context really drives the stacks (AC15, AC12) -------------------------------------


def test_synthesized_feed_api_cors_origins_equal_the_files_list():
    pinned = read_pinned_context()
    expected = [o.strip() for o in pinned["feed_api_allowed_origins"].split(",") if o.strip()]
    template = synth_stack("AiRadarFeedApi", pinned)
    apis = [r for r in template["Resources"].values() if r["Type"] == "AWS::ApiGatewayV2::Api"]
    assert len(apis) == 1
    assert apis[0]["Properties"]["CorsConfiguration"]["AllowOrigins"] == expected


def test_pinned_context_makes_both_apis_omit_the_lambda_reservation():
    pinned = read_pinned_context()
    for name in ("AiRadarFeedApi", "AiRadarChatApi"):
        template = synth_stack(name, pinned)
        fns = [r for r in template["Resources"].values() if r["Type"] == "AWS::Lambda::Function"]
        assert fns, name
        assert all("ReservedConcurrentExecutions" not in f["Properties"] for f in fns), name


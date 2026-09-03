"""Regression test for `Dockerfile.feed_api` (feed-api spec 01).

Spec: specs/feed-api/contract.md "`Dockerfile.feed_api` — CREATE (repo root;
build context = repo root)", AD-1, AD-2; specs/feed-api/audit.md T24.

Trimmed (2026-09-01, per human review) to exactly the tests that guard a
regression a successful `cdk deploy` would NOT surface — a wrong/missing base
image or a genuinely absent Dockerfile fails loudly and immediately at deploy
or first invoke, so those checks were dropped as redundant with that natural
feedback loop. What survives are the three **silent** failure modes: a
packaging-mechanism regression that still builds and deploys but bloats the
image or breaks reproducibility (AD-1/AD-2), a Plane A boundary leak that a
successful deploy would never reveal, and a handler-wiring typo that only
surfaces on the first real invoke. Functional assertions parsed from the
Dockerfile's instructions (not a broad text-diff/change-detector) — no
`docker build` is run (contract.md: image assets are built by the CDK CLI at
deploy time, and this repo's tests stay Docker-free).

RED phase: `Dockerfile.feed_api` does not exist yet. Every test in this file
is expected to fail with a clear "file must exist" assertion (not a
collection-time ImportError, since this file parses text, not Python) until
Phase 3 (tasks.md Task 3.5) lands.
"""
from __future__ import annotations

from pathlib import Path

DOCKERFILE_PATH = Path(__file__).parent.parent / "Dockerfile.feed_api"


def _logical_lines(text: str) -> list[str]:
    """Join `\\`-continued lines into single logical Dockerfile instructions,
    mirroring `tests/test_dockerfile.py::_env_assignments`'s line-joiner."""
    logical_lines: list[str] = []
    buffer = ""
    for raw_line in text.splitlines():
        stripped = raw_line.rstrip()
        if buffer:
            stripped = buffer + " " + stripped.strip()
            buffer = ""
        if stripped.endswith("\\"):
            buffer = stripped[:-1].rstrip()
            continue
        logical_lines.append(stripped)
    if buffer:
        logical_lines.append(buffer)
    return logical_lines


def _instructions(keyword: str) -> list[str]:
    """All logical lines starting with the given Dockerfile instruction
    keyword (e.g. "RUN", "COPY", "CMD"), keyword stripped off. Also the
    file-existence guard for every test below — a missing Dockerfile fails
    here with a clear message rather than each test re-asserting it."""
    assert DOCKERFILE_PATH.is_file(), f"expected {DOCKERFILE_PATH} to exist"
    text = DOCKERFILE_PATH.read_text()
    prefix = f"{keyword} "
    return [
        line[len(prefix):].strip()
        for line in _logical_lines(text)
        if line.strip().startswith(prefix)
    ]


# AD-1/AD-2: the actual reason this spec chose Docker+uv over the rejected
# packaging alternatives. A regression here (a bare `pip install` slipping
# in, a missing `--only-group api`/`--frozen`) still builds and deploys
# successfully — it just silently bloats the image or breaks
# reproducibility, which a deploy would never surface.
def test_dependencies_are_installed_via_uv_export_with_only_group_api():
    run_lines = _instructions("RUN")
    combined = " ".join(run_lines)
    assert "uv export" in combined, "AD-2: dependencies must be resolved from uv.lock via `uv export`"
    assert "--only-group api" in combined, (
        "AD-2: the image must install ONLY the `api` dependency group "
        "(pydantic) — not langgraph/bedrock-agentcore/tavily-python/feedparser/rich"
    )
    assert "--frozen" in combined, "must not silently update uv.lock at build time"

    # Every occurrence of "pip install" in this Dockerfile must be
    # immediately preceded by "uv " (i.e. `uv pip install`, `uv`'s own
    # installer subcommand) — a bare `pip install` would reintroduce a
    # second packaging mechanism (AD-1/AD-2: "no pip, no requirements.txt
    # checked in").
    for line in run_lines:
        index = line.find("pip install")
        while index != -1:
            preceding = line[max(0, index - 3):index]
            assert preceding == "uv ", (
                f"found a bare `pip install` (not `uv pip install`) in: {line!r}"
            )
            index = line.find("pip install", index + 1)


# A real architecture/security boundary a successful deploy would never
# reveal: Plane A internals leaking into the public-facing read-API image.
def test_copies_only_api_and_contracts_never_curation_or_shared():
    copy_lines = _instructions("COPY")
    combined = " ".join(copy_lines)
    assert "src/api" in combined, "expected src/api/ to be copied into the image"
    assert "src/contracts" in combined, "expected src/contracts/ to be copied into the image"
    assert "src/curation" not in combined, (
        "src/curation must NOT be copied — Plane A internals have no business "
        "in the read-API image"
    )
    assert "src/shared" not in combined, (
        "src/shared must NOT be copied (AD-3: the Lambda does not use shared.config)"
    )


# The one test that connects the Dockerfile to api.handler.handler — a typo
# here only surfaces on the first real invoke, not at deploy.
def test_cmd_points_at_the_handler_entrypoint():
    cmd_lines = _instructions("CMD")
    assert len(cmd_lines) == 1, "expected exactly one CMD instruction"
    cmd = cmd_lines[0]
    assert "api.handler.handler" in cmd, (
        f"expected CMD to reference api.handler.handler, got: {cmd!r}"
    )

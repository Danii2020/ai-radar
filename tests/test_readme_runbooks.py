"""README runbook commands stay runnable (spec backend-cicd-pipeline, outcome O18; AC12,
audit finding F4).

Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation row AC12 (README runbook
commands are intact). A `#` comment line after a line that ends in a backslash ends the
command in bash, so the rest of the continued command runs as a separate (failing) command and
silently drops its flags. That is how the feed-api CORS hand-deploy lost
`-c feed_api_reserved_concurrency=none`.

The check is static text over fenced `bash` / `sh` blocks. The last two tests prove the
detector itself on fixture blocks (a comment inside a continued command is flagged, a comment
outside one is not).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
FENCE = re.compile(r"^\s*```(?P<lang>[A-Za-z0-9_-]*)\s*$")


def _shell_blocks(markdown: str) -> list[tuple[int, list[str]]]:
    """(first line number, lines) of every fenced bash/sh/shell block."""
    blocks: list[tuple[int, list[str]]] = []
    lang: str | None = None  # None: outside any fence
    start = 0
    lines: list[str] = []
    for number, line in enumerate(markdown.splitlines(), start=1):
        fence = FENCE.match(line)
        if fence and lang is None:
            lang, start, lines = fence.group("lang"), number + 1, []
        elif fence:
            if lang in {"bash", "sh", "shell"}:
                blocks.append((start, lines))
            lang = None
        elif lang is not None:
            lines.append(line)
    return blocks


def _comments_inside_continuations(lines: list[str]) -> list[int]:
    """Indexes of comment lines that directly follow a line ending in a backslash."""
    return [
        i
        for i in range(1, len(lines))
        if lines[i].lstrip().startswith("#") and lines[i - 1].rstrip().endswith("\\")
    ]


def test_no_readme_shell_block_has_a_comment_line_inside_a_continued_command():
    readme = (REPO / "README.md").read_text()
    blocks = _shell_blocks(readme)
    assert blocks, "found no bash blocks in README.md"
    offenders = [
        f"README.md line {start + i}: {lines[i].strip()}"
        for start, lines in blocks
        for i in _comments_inside_continuations(lines)
    ]
    assert offenders == []


def test_detector_flags_a_comment_placed_inside_a_backslash_continuation():
    block = ["uv run cdk deploy A \\", "  -c a=b \\", "  # note", "  -c c=d"]
    assert _comments_inside_continuations(block) == [2]


def test_detector_accepts_comments_before_or_after_a_continued_command():
    block = ["# note", "uv run cdk deploy A \\", "  -c a=b   # trailing note is fine", "# after"]
    assert _comments_inside_continuations(block) == []

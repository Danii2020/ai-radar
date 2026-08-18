"""Bedrock layer — summarize + tag one item into a structured card via Claude Haiku.

Uses the Converse API with a forced tool call so the model always returns
well-formed structured output (no brittle JSON-from-prose parsing).
"""
from __future__ import annotations

from dataclasses import dataclass

import boto3

from .config import AWS_REGION, HAIKU_MODEL_ID
from .feeds import RawItem


@dataclass(frozen=True)
class TokenUsage:
    """Bedrock Converse token accounting for ONE model call.

    Mirrors the `usage` block of a Converse response (botocore shape
    `TokenUsage`: `inputTokens` / `outputTokens` / `totalTokens` are required;
    the cache fields are optional and unused here — `summarize` sets no cache
    point). Plain data: carried out of the infra edge so `curation.nodes` can
    accumulate token counts without ever importing boto3.
    """

    input_tokens: int = 0
    output_tokens: int = 0

_client = None


def bedrock_client():
    """Shared bedrock-runtime client (lazy singleton)."""
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _client


SYSTEM = (
    "You are an AI-news curation assistant for an app that keeps practitioners "
    "up to date on AI / GenAI / LLM / ML / DL. For each item you receive, produce "
    "a concise, neutral, accurate card. Summarize only what the source supports — "
    "never invent details. Write for a technical but time-poor reader."
)

# Forced tool = guaranteed structured output.
CARD_TOOL = {
    "toolSpec": {
        "name": "emit_card",
        "description": "Emit the structured curation card for one AI-news item.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Clear, normalized headline (no clickbait, no source prefix).",
                    },
                    "summary": {
                        "type": "string",
                        "description": "2-4 sentence neutral summary of what this is and why it matters.",
                    },
                    "takeaways": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "1-3 short, concrete key takeaways.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "3-6 lowercase topic tags, e.g. 'llm', 'rag', 'agents', 'training'.",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["news", "paper", "project", "concept", "release"],
                        "description": "What kind of item this is.",
                    },
                    "relevance": {
                        "type": "integer",
                        "description": "1-10 relevance/trendiness for a working AI practitioner.",
                    },
                },
                "required": ["title", "summary", "tags", "type", "relevance"],
            }
        },
    }
}


def summarize_with_usage(item: RawItem) -> tuple[dict, TokenUsage]:
    """Same Converse call as `summarize`, returning the card dict AND the
    call's token usage.

    Missing/malformed `usage` degrades to `TokenUsage(0, 0)` — a cost figure
    is never worth failing a run over. Raises `RuntimeError` when the model
    returns no `toolUse` block (unchanged behavior).
    """
    user_text = (
        f"Source: {item.source}\n"
        f"Original title: {item.title}\n"
        f"Published: {item.published or 'unknown'}\n"
        f"URL: {item.url}\n\n"
        f"Content snippet:\n{item.snippet or '(no snippet provided)'}"
    )

    resp = bedrock_client().converse(
        modelId=HAIKU_MODEL_ID,
        system=[{"text": SYSTEM}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        toolConfig={
            "tools": [CARD_TOOL],
            "toolChoice": {"tool": {"name": "emit_card"}},
        },
        inferenceConfig={"maxTokens": 700, "temperature": 0.2},
    )

    usage_block = resp.get("usage", {}) or {}
    try:
        input_tokens = int(usage_block.get("inputTokens", 0))
        output_tokens = int(usage_block.get("outputTokens", 0))
    except (TypeError, ValueError, AttributeError):
        # TypeError/ValueError: inputTokens/outputTokens present but not
        # int-coercible. AttributeError: `usage` itself is some non-mapping
        # truthy value (e.g. a list) that has no `.get` at all - `or {}`
        # above only catches the falsy case. Any shape of bad `usage` data
        # degrades to zero usage (see docstring), never fails the item.
        input_tokens = 0
        output_tokens = 0
    usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)

    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block:
            return block["toolUse"]["input"], usage
    raise RuntimeError("Model did not return a card (no toolUse block).")


def summarize(item: RawItem) -> dict:
    """UNCHANGED public signature and return value (Phase 0 + Plane B
    callers depend on it). Now a one-line wrapper:
    `return summarize_with_usage(item)[0]`.
    """
    return summarize_with_usage(item)[0]

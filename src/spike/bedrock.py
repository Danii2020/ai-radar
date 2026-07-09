"""Bedrock layer — summarize + tag one item into a structured card via Claude Haiku.

Uses the Converse API with a forced tool call so the model always returns
well-formed structured output (no brittle JSON-from-prose parsing).
"""
from __future__ import annotations

import boto3

from .config import AWS_REGION, HAIKU_MODEL_ID
from .feeds import RawItem

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


def summarize(item: RawItem) -> dict:
    """Return a dict card (title, summary, takeaways, tags, type, relevance)."""
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

    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block:
            return block["toolUse"]["input"]
    raise RuntimeError("Model did not return a card (no toolUse block).")

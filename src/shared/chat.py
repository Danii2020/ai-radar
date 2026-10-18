"""Mini RAG chat (Plane B) — answer questions grounded in curated cards.

Retrieves top-k cards per turn, injects them as cited context, and answers with
Claude Sonnet. Keeps a lightweight multi-turn history. The stable system prompt
is marked with a Bedrock cachePoint so repeated turns hit the prompt cache.
"""
from __future__ import annotations

from typing import Protocol

from .bedrock import bedrock_client
from .config import SONNET_MODEL_ID, TOP_K


class Retriever(Protocol):
    """Anything that can rank stored cards against a question: the local
    `CardIndex` and the DynamoDB `DynamoCardRetriever`."""

    def search(self, query: str, k: int) -> list[tuple[dict, float]]: ...


SYSTEM = (
    "You are AI Radar's assistant. You help users dig into AI / GenAI / LLM / ML "
    "news that the app has already collected. Answer ONLY from the provided context "
    "cards — never from prior knowledge. Cite sources inline as [1], [2], matching "
    "the numbered cards. If the context does not contain the answer, say so plainly "
    "and suggest what the user could ask instead. Be concise and concrete."
)


def _context_block(hits: list[tuple[dict, float]]) -> str:
    lines = []
    for i, (card, _score) in enumerate(hits, 1):
        lines.append(
            f"[{i}] {card['title']} ({card['source']}, {card.get('published') or 'n/a'})\n"
            f"    {card['summary']}\n"
            f"    url: {card['url']}"
        )
    return "\n\n".join(lines)


def answer_question(
    question: str,
    prior_messages: list[dict],
    hits: list[tuple[dict, float]],
) -> str:
    """Stateless answer step shared by `RagChat` and the chat agent.

    `prior_messages` are earlier turns in Converse form; they are sent verbatim
    before this turn's context-augmented question. Holds no state.
    """
    augmented = (
        f"Context cards:\n\n{_context_block(hits)}\n\n"
        f"User question: {question}"
    )
    messages = list(prior_messages) + [
        {"role": "user", "content": [{"text": augmented}]}
    ]
    resp = bedrock_client().converse(
        modelId=SONNET_MODEL_ID,
        system=[{"text": SYSTEM}, {"cachePoint": {"type": "default"}}],
        messages=messages,
        inferenceConfig={"maxTokens": 800, "temperature": 0.3},
    )
    return resp["output"]["message"]["content"][0]["text"]


class RagChat:
    """Stateful RAG chat over a `Retriever`."""

    def __init__(self, retriever: Retriever, k: int = TOP_K):
        self.retriever = retriever
        self.k = k
        self.history: list[dict] = []  # plain user/assistant turns (no context bloat)

    def ask(self, question: str) -> tuple[str, list[tuple[dict, float]]]:
        hits = self.retriever.search(question, self.k)
        answer = answer_question(question, self.history, hits)

        # Store the *original* question (not the augmented one) to keep history lean.
        self.history.append({"role": "user", "content": [{"text": question}]})
        self.history.append({"role": "assistant", "content": [{"text": answer}]})
        return answer, hits

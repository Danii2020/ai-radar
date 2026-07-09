"""Mini RAG chat (Plane B) — answer questions grounded in curated cards.

Retrieves top-k cards per turn, injects them as cited context, and answers with
Claude Sonnet. Keeps a lightweight multi-turn history. The stable system prompt
is marked with a Bedrock cachePoint so repeated turns hit the prompt cache.
"""
from __future__ import annotations

from .bedrock import bedrock_client
from .config import SONNET_MODEL_ID, TOP_K
from .retrieval import CardIndex

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


class RagChat:
    """Stateful RAG chat over a CardIndex."""

    def __init__(self, cards: list[dict], k: int = TOP_K):
        self.index = CardIndex(cards)
        self.k = k
        self.history: list[dict] = []  # plain user/assistant turns (no context bloat)

    def ask(self, question: str) -> tuple[str, list[tuple[dict, float]]]:
        hits = self.index.search(question, self.k)
        augmented = (
            f"Context cards:\n\n{_context_block(hits)}\n\n"
            f"User question: {question}"
        )

        # Rebuild the request: prior turns verbatim + this turn's augmented question.
        messages = self.history + [
            {"role": "user", "content": [{"text": augmented}]}
        ]

        resp = bedrock_client().converse(
            modelId=SONNET_MODEL_ID,
            system=[{"text": SYSTEM}, {"cachePoint": {"type": "default"}}],
            messages=messages,
            inferenceConfig={"maxTokens": 800, "temperature": 0.3},
        )
        answer = resp["output"]["message"]["content"][0]["text"]

        # Store the *original* question (not the augmented one) to keep history lean.
        self.history.append({"role": "user", "content": [{"text": question}]})
        self.history.append({"role": "assistant", "content": [{"text": answer}]})
        return answer, hits

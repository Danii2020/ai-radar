"""LangGraph node factories — closures bound to the injected `Discoverer` /
`CardStore` dependencies.

Portability constraint: no `boto3` import here — the only Bedrock touchpoint
is the existing `shared.bedrock.summarize_with_usage` helper, imported as-is.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Protocol

from shared.bedrock import summarize_with_usage
from shared.cards import Card
from shared.embeddings import card_text, embed

from .interfaces import CardStore, Discoverer, EmbeddingWriter
from .state import CurationState

logger = logging.getLogger(__name__)     # "curation.nodes" — handlers are the
                                         # composition root's job (runtime_app
                                         # attaches the SDK's; run_curation.py
                                         # uses basicConfig)


def _log(event: str, state: CurationState, **fields) -> None:
    """One structured JSON record: `{"event": ..., "run_id": ..., **fields}`.
    `run_id` comes from the state (empty string when the caller did not set
    one). Node-level only — never per item."""
    logger.info(
        json.dumps({"event": event, "run_id": state.get("run_id", ""), **fields})
    )


class NodeFn(Protocol):
    """Shape LangGraph's `add_node` expects: a `state`-keyword-callable.

    `Callable[[CurationState], CurationState]` erases the parameter name and
    is treated as position-only, which doesn't structurally match LangGraph's
    node Protocol (`__call__(self, state: ...) -> Any`) — this named-Protocol
    form does.
    """

    def __call__(self, state: CurationState) -> CurationState: ...


def discover_node(discoverer: Discoverer) -> NodeFn:
    def _discover(state: CurationState) -> CurationState:
        raw = discoverer.discover()
        discovered_by_source: dict[str, int] = dict(Counter(item.source for item in raw))
        _log(
            "discover_complete",
            state,
            discovered=len(raw),
            discovered_by_source=discovered_by_source,
        )
        return {
            "raw": raw,
            "discovered": len(raw),
            "discovered_by_source": discovered_by_source,
        }

    return _discover


def dedup_node(store: CardStore) -> NodeFn:
    def _dedup(state: CurationState) -> CurationState:
        raw = state.get("raw", [])
        max_items = state.get("max_items")
        fresh_before_cap = store.dedup_filter(raw)
        fresh = fresh_before_cap[:max_items] if max_items is not None else fresh_before_cap
        return {"fresh": fresh, "deduped": len(fresh_before_cap)}

    return _dedup


def summarize_node(state: CurationState) -> CurationState:
    fresh = state.get("fresh", [])
    cards: list[Card] = []
    failed = 0
    input_tokens = 0
    output_tokens = 0
    for item in fresh:
        try:
            model_out, usage = summarize_with_usage(item)
            input_tokens += usage.input_tokens
            output_tokens += usage.output_tokens
            cards.append(Card.from_model(item, model_out))
        except Exception as exc:  # noqa: BLE001 - per-item failure: skip, count, continue
            logger.warning(
                json.dumps(
                    {
                        "event": "summarize_item_failed",
                        "run_id": state.get("run_id", ""),
                        "url": item.url,
                        "error": str(exc),
                    }
                )
            )
            failed += 1
    _log(
        "summarize_complete",
        state,
        summarized=len(cards),
        failed=failed,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    return {
        "cards": cards,
        "summarized": len(cards),
        "failed": failed,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def rank_node(state: CurationState) -> CurationState:
    cards = state.get("cards", [])
    ranked = sorted(cards, key=lambda c: c.relevance, reverse=True)
    return {"cards": ranked}


def persist_node(store: CardStore) -> NodeFn:
    def _persist(state: CurationState) -> CurationState:
        cards = state.get("cards", [])
        store.upsert(cards)
        _log("persist_complete", state, persisted=len(cards))
        return {"persisted": len(cards)}

    return _persist


def embed_node(writer: EmbeddingWriter) -> NodeFn:
    """Runs after persist. Embedding is best-effort: a Titan failure on one card
    or a failed write is counted and logged, never raised (AC2)."""

    def _embed(state: CurationState) -> CurationState:
        vectors: dict[str, list[float]] = {}
        failed = 0
        for card in state.get("cards", []):
            try:
                vectors[card.url] = embed(card_text(card.to_dict()))
            except Exception as exc:  # noqa: BLE001 - per-card failure: skip, count, continue
                logger.warning(
                    json.dumps(
                        {
                            "event": "embed_item_failed",
                            "run_id": state.get("run_id", ""),
                            "url": card.url,
                            "error": str(exc),
                        }
                    )
                )
                failed += 1
        embedded = 0
        if vectors:
            try:
                embedded = writer.set_embeddings(vectors)
                failed += len(vectors) - embedded
            except Exception as exc:  # noqa: BLE001 - a failed write must not fail the run
                logger.warning(
                    json.dumps(
                        {
                            "event": "embed_write_failed",
                            "run_id": state.get("run_id", ""),
                            "error": str(exc),
                        }
                    )
                )
                failed += len(vectors)
        _log("embed_complete", state, embedded=embedded, embed_failed=failed)
        return {"embedded": embedded, "embed_failed": failed}

    return _embed

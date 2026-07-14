"""LangGraph node factories — closures bound to the injected `Discoverer` /
`CardStore` dependencies.

Portability constraint: no `boto3` import here — the only Bedrock touchpoint
is the existing `spike.bedrock.summarize` helper, imported as-is.
"""
from __future__ import annotations

from typing import Protocol

from spike.bedrock import summarize
from spike.cards import Card

from .interfaces import CardStore, Discoverer
from .state import CurationState


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
        return {"raw": raw, "discovered": len(raw)}

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
    for item in fresh:
        try:
            model_out = summarize(item)
            cards.append(Card.from_model(item, model_out))
        except Exception as exc:  # per-item failure: skip, count, continue
            print(f"  ! failed to summarize {item.url}: {exc}")
            failed += 1
    return {"cards": cards, "summarized": len(cards), "failed": failed}


def rank_node(state: CurationState) -> CurationState:
    cards = state.get("cards", [])
    ranked = sorted(cards, key=lambda c: c.relevance, reverse=True)
    return {"cards": ranked}


def persist_node(store: CardStore) -> NodeFn:
    def _persist(state: CurationState) -> CurationState:
        cards = state.get("cards", [])
        store.upsert(cards)
        return {}

    return _persist

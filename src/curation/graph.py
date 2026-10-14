"""Public construction API — the single entry point Specs 02-04 call into."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .interfaces import CardStore, Discoverer, EmbeddingWriter
from .nodes import (
    dedup_node,
    discover_node,
    embed_node,
    persist_node,
    rank_node,
    summarize_node,
)
from .state import CurationState


def build_graph(
    store: CardStore,
    discoverer: Discoverer,
    embedding_writer: EmbeddingWriter | None = None,
):
    """Build and compile the curation StateGraph.

    Wires nodes discover -> dedup -> summarize -> rank -> persist with
    `discoverer` and `store` captured by closure (dependency injection).
    Returns the compiled graph (langgraph CompiledStateGraph); call
    `.invoke({"max_items": N})` to run it.

    With an `embedding_writer`, an `embed` node follows `persist` (a Titan or
    write failure never un-persists a card); without one the graph is unchanged.

    The compiled graph is PURE LOGIC: no node closes over boto3, file paths,
    or DynamoDB — only over `store`, `discoverer`, and `bedrock.summarize`.
    """
    graph = StateGraph(CurationState)

    graph.add_node("discover", discover_node(discoverer))
    graph.add_node("dedup", dedup_node(store))
    graph.add_node("summarize", summarize_node)
    graph.add_node("rank", rank_node)
    graph.add_node("persist", persist_node(store))

    graph.add_edge(START, "discover")
    graph.add_edge("discover", "dedup")
    graph.add_edge("dedup", "summarize")
    graph.add_edge("summarize", "rank")
    graph.add_edge("rank", "persist")
    if embedding_writer is not None:
        graph.add_node("embed", embed_node(embedding_writer))
        graph.add_edge("persist", "embed")
        graph.add_edge("embed", END)
    else:
        graph.add_edge("persist", END)

    return graph.compile()

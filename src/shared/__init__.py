"""AI Radar — modules shared across both planes.

Cross-plane: `config` (region, model IDs, tuning, cache paths), `bedrock`
(lazy Bedrock client + Haiku summarize), `cards` (the `Card` contract +
console rendering), `feeds` (RSS/Atom discovery -> `RawItem`).

Plane B: `chat` (grounded RAG answers), `retrieval` (Titan embeddings +
cosine `CardIndex`). Plane A lives in `curation/`. The planes never import
each other's internals — `Card` is the only shared contract
(`docs/architecture-principles.md`).
"""

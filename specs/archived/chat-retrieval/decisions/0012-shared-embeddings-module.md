# ADR 0012: The Titan embedding call and card text live in a neutral shared module

- **Status**: Accepted
- **Date**: 2026-10-13
- **Feature**: chat-retrieval
- **Capability**: chat-retrieval
- **Source**: execution-plan.md § Proposed approach (decision: `shared/embeddings.py` owns `embed(text)` and `card_text(mapping)`)
- **Trigger**: (a) a choice between named options (move into `shared`, import from `shared.retrieval`, duplicate); (b) it fixes where both planes obtain vectors, which constrains future embedding work

## Context
Plane A (curation) must embed cards at persist time. Plane B (retrieval) must embed the question and the cards. The architecture principles forbid either plane from importing the other's internals. `shared/retrieval.py` and `shared/chat.py` are Plane B by naming only (the `rename-spike-to-shared` contract). The card-to-text rule must match Phase 0's `_card_text` exactly, or stored vectors and query vectors would drift apart.

## Decision
`src/shared/embeddings.py` owns `embed(text)`, the Titan v2 call with `dimensions=EMBED_DIM` and `normalize=True`, and `card_text(card)`, the Phase 0 rule moved verbatim. `shared/retrieval.py` imports both. Plane A imports `shared.embeddings`, never `shared.retrieval`.

## Alternatives considered
| Option | Why not |
|---|---|
| Curation imports `shared.retrieval` | Crosses the plane boundary, and the plane rule forbids it. |
| Duplicate the Titan call in `curation` | Two copies of the embedding rule would drift, and the card text must match exactly. |
| A new top-level `src/embeddings/` package | Heavier than two functions need. |

## Consequences
**Positive**: one embedding rule for both planes. An AST guard in `tests/test_chat_contract.py` keeps the planes apart.
**Accepted costs**: Plane B code still sits under `shared/`, by the earlier naming decision. Moving it later would mean updating imports.

## Follow-ups
- None.

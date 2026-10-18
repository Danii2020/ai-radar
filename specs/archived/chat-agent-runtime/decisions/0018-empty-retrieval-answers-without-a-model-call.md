# ADR 0018: When retrieval returns nothing, the chat answers with a fixed message and makes no model call

- **Status**: Accepted
- **Date**: 2026-10-18
- **Feature**: chat-agent-runtime
- **Capability**: chat-agent
- **Source**: execution-plan.md § Proposed approach (Decision: when `retrieve` returns no hits); intent.md § AC4
- **Trigger**: (a) it chooses between a fixed answer and calling Sonnet with an empty context block; (b) it sets a grounding rule future chat paths must follow

## Context
With an empty or fully un-embedded corpus, the chat has no card to ground an answer in. The grounding rule (AC4) says the agent must say the context does not contain the answer, return `sources: []`, and invent no `[n]` citation. A model called with an empty context block could produce any answer, and the Phase 0 prompt does not define that case.

## Decision
When `retrieve` returns no hits, the `answer` node returns a fixed "the collected news does not contain this" message with `sources: []`. It makes **no** model call.

## Alternatives considered
| Option | Why not |
|---|---|
| Call Sonnet with an empty context block and rely on the system prompt | The output is non-deterministic and the prompt does not cover the case. The model could still hallucinate a citation. It also costs a Sonnet call for nothing. |
| Return an error instead of an answer | AC4 requires an answer. An error would also turn a valid empty corpus into a failure. |

## Consequences
**Positive**: deterministic, cheaper, and it cannot produce a citation, because no model output exists on that path. `retrieval_ms` is still logged, and `outcome` is `no_context`.
**Accepted costs**: the fixed message is English-only and generic. A follow-up question with no hits gets the same message, which is correct but not helpful. The model is never asked to say that the answer is missing from the context.

## Follow-ups
- None. The no-hits path is covered by tests that assert zero model calls.

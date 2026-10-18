# ADR 0019: The request rules and caps are pinned values, validated before any AWS call, with rule names as the error detail

- **Status**: Accepted
- **Date**: 2026-10-18
- **Feature**: chat-agent-runtime
- **Capability**: chat-agent
- **Source**: execution-plan.md § Proposed approach (Decision: validation rules, pinned here because `Converse` requires them; Decision: request handling order in the handler); § Binding constraints (config through `pydantic-settings`, explicit `validation_alias`, fail-fast); intent.md § AC3
- **Trigger**: (b) the rule names, the caps and the alternation rule are a contract that every future client of the agent must obey; (a) it chooses fixed caps over an unbounded history

## Context
The agent passes the client's history straight into a Converse call, and a single turn carries text into a model that bills per token. Converse also rejects some shapes outright, for example a history that does not alternate roles. The intent (AC3) pins the caps. The plan adds the alternation rule, because Converse requires it. A rejection must never echo the input, since the input is untrusted client text and AC6 forbids question text in logs.

## Decision
`parse_request` (`src/chat/request.py`, pure) runs before the graph and before any client is touched. It enforces these rules: a non-empty `question` of at most `CHAT_MAX_QUESTION_CHARS` (1000); a `history` that defaults to `[]`, has at most `CHAT_MAX_HISTORY_TURNS` × 2 items (10 turns, so 20 items), and has alternating roles that start with `user` and end with `assistant`; and each item has a non-empty `text` of at most `CHAT_MAX_HISTORY_ITEM_CHARS` (4000). These caps are typed pydantic-settings fields with explicit `validation_alias`. A failure returns `{"error": "invalid_request", "detail": "<rule name>"}`, and the rule name is fixed text, never the input.

## Alternatives considered
| Option | Why not |
|---|---|
| Let Converse or the model reject bad input | Converse raises a generic error that becomes `upstream_failure`. That spends a Bedrock call and hides the cause, and it lets oversized text reach the model. |
| Echo the rejected value in `detail` | The input is untrusted and may be long. Echoing it leaks text into the response and invites injection. |
| Unbounded history | Every turn would pay for the whole conversation, and the token cost would grow with it. |

## Consequences
**Positive**: an invalid request makes no retrieval and no model call, which the tests assert. The caps bound the tokens per turn. Future clients get a stable, documented error contract, and the rule names are the only text they see.
**Accepted costs**: the caps are a product decision, so changing one needs a spec change and a test change, not just an environment change. The alternation rule has its own test only after an audit round.

## Follow-ups
- A future `chat-api` may add its own limits in front of these, but must not loosen these.

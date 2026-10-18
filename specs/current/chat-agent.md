# Chat Agent Specification

> Last synced: 2026-10-18. Owned artifacts: `chat_app.py`, `src/chat/request.py`,
> `src/chat/graph.py`, `src/chat/config.py` (the `CHAT_MAX_*` caps), `src/shared/chat.py`
> (`answer_question`). Deployed 2026-10-18 as AgentCore Runtime agent `ai_radar_chat`
> (`ai_radar_chat-JFCO0R9lkT`).

## Purpose

The RAG chat served as an agent: one stateless turn in, one grounded answer out. Its
request, response, error and statelessness contract is what a future caller (the chat
API, `chat-api`) depends on. That contract is its own capability. Retrieval is
`chat-retrieval`, and packaging and the execution role are `runtime-deployment`. The chat
model is Sonnet 4.6 (the `SONNET_MODEL_ID` default, ADR 0021).

## Requirements

### Requirement: CA-1 — A turn returns an answer and its ranked sources, nothing else

The system SHALL answer one turn with `{"answer": str, "sources": [...]}`. Each source SHALL
carry exactly `n`, `title`, `url`, `source`, `published` and `score`, with `n` matching the
`[n]` in the answer. A source SHALL NOT carry a vector or any other field, such as a
`request_id`.

**Source:** chat-agent-runtime · intent.md § AC1

#### Scenario: A card with a vector and a relevance field is returned
- **WHEN** a turn retrieves a card that carries `embedding` and `relevance`
- **THEN** the response's source has only `n, title, url, source, published, score`, and `score` is rounded to 4 places

### Requirement: CA-2 — Turns are stateless

The system SHALL take the prior turns from the request's `history`, as ordered
`{"role": "user" | "assistant", "text": str}` items. Nothing from one invocation SHALL
survive into the next. The same inputs SHALL give the same model request, whatever the
process served before.

**Source:** chat-agent-runtime · intent.md § AC2

#### Scenario: A follow-up turn carries its history
- **WHEN** turn 2 is sent with turn 1's question and answer in `history`
- **THEN** the model request holds those messages in order, before turn 2's question

#### Scenario: A later invocation without history
- **WHEN** an invocation is sent after another one, with `history` empty
- **THEN** the model request holds only the new question and the context, with nothing from the earlier invocation

### Requirement: CA-3 — A request is validated and capped before any AWS call

The system SHALL reject a request that breaks a rule and return `{"error": "invalid_request",
"detail": "<rule name>"}`, without a retrieval or model call. The rules are: a missing or
empty `question`; a `question` over 1,000 characters; a `history` that is not a list of
well-formed items; more than 10 turns (20 items); a single history item over 4,000 characters;
and history roles that do not alternate, starting with `user` and ending with `assistant`.
`detail` SHALL be a fixed rule name, never an echo of the input.

**Source:** chat-agent-runtime · intent.md § AC3; execution-plan.md § Proposed approach (validation rules)

#### Scenario: An empty question
- **WHEN** the payload is `{"question": ""}`
- **THEN** the response is `invalid_request` with `detail` `question_empty`, and neither the retriever nor the model is called

#### Scenario: A question of exactly 1,000 characters
- **WHEN** the question is 1,000 characters long
- **THEN** the turn is answered, and a question of 1,001 characters returns `invalid_request`

### Requirement: CA-4 — Answers are grounded, including when nothing is retrieved

The system SHALL answer only from the retrieved cards, and it SHALL cite only numbered sources
that it returned. When retrieval returns nothing (an empty or fully un-embedded corpus), the
system SHALL return a fixed "the collected news does not contain this" answer with
`sources: []`, and SHALL NOT call the model.

**Source:** chat-agent-runtime · intent.md § AC4; execution-plan.md § Proposed approach (no-hits decision)

#### Scenario: An empty table
- **WHEN** the card table has no cards
- **THEN** the response is the no-context answer with `sources == []`, and no model call is made

### Requirement: CA-5 — Upstream failures are logged and returned as a typed error

The system SHALL, when a retrieval or model call fails during a turn, log the exception with
its stack trace and return `{"error": "upstream_failure"}`. The process SHALL keep serving the
next invocation.

**Source:** chat-agent-runtime · intent.md § AC5

#### Scenario: The model call throws
- **WHEN** the model call raises during a turn
- **THEN** the response is `upstream_failure`, the record `chat_turn_failed` carries the traceback, and the next valid invocation succeeds

### Requirement: CA-6 — Each turn writes one log record without any text

The system SHALL write one `chat_turn` structured log record per invocation, with
`question_chars`, `history_items`, `hits`, `retrieval_ms`, `model_ms` and `outcome`
(`ok`, `no_context`, `invalid_request` or `upstream_failure`). The record SHALL NOT contain the
question, the history or the answer text.

**Source:** chat-agent-runtime · intent.md § AC6; execution-plan.md § Proposed approach (logging decision)

#### Scenario: A normal turn
- **WHEN** a turn is answered from four hits
- **THEN** exactly one `chat_turn` record is written, with `outcome: ok`, `hits: 4`, and no `question` or answer key

## Invariants

1. Statelessness holds at the graph level. The graph is compiled without a checkpointer, and
   no conversation state lives in module scope. A turn's model request depends only on its
   payload (CA-2).
2. The graph and request modules (`src/chat/graph.py`, `src/chat/request.py`) build no AWS
   client, and `bedrock_agentcore` is imported only by the root `chat_app.py`. `src/chat`
   imports only `shared` and its own modules (CR-9 in `chat-retrieval`).
3. The model is called only with a non-empty set of retrieved cards. An empty retrieval never
   reaches the model (CA-4).

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| CAR-F5 | The `empty-text` param in `tests/test_chat_app.py` is a bare list, so it exercises `payload_not_object`, not empty item text. Empty text is covered elsewhere. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F5) |
| CAR-F6 | The plan's focused `-k` selectors miss some tests, so the broad command is the reliable gate. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F6) |
| CAR-F7 | On `upstream_failure`, `chat_turn` reports `hits=0` and `retrieval_ms=0` even when retrieval succeeded, so the partial latency is lost. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F7) |
| CAR-F8 | CI (`harny-feedback.yml`) has not run on a PR for this change, because the branch is not pushed. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F8) |
| CAR-F11 | The latency and card-count evidence for AC10 step 8 is one sample (`retrieval_ms=330`) against 16 live cards. There is no p95 against the ADR 0009 ceiling. Accepted by the human on 2026-10-18. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F11) |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| chat-agent-runtime | 2026-10-18 | CA-1..CA-6: the stateless `{question, history}` → `{answer, sources}` agent contract, its request validation and caps, the no-context grounding path, the upstream-failure contract, and the text-free `chat_turn` record. Deployed as `ai_radar_chat`. |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0016](../archived/chat-agent-runtime/decisions/0016-one-stateless-synchronous-chat-entrypoint.md) | The chat agent is one stateless, synchronous request-response entrypoint | Accepted |
| [0018](../archived/chat-agent-runtime/decisions/0018-empty-retrieval-answers-without-a-model-call.md) | When retrieval returns nothing, the chat answers with a fixed message and makes no model call | Accepted |
| [0019](../archived/chat-agent-runtime/decisions/0019-request-rules-and-caps-pinned-as-typed-settings.md) | The request rules and caps are pinned values, validated before any AWS call, with rule names as the error detail | Accepted |
| [0021](../archived/chat-agent-runtime/decisions/0021-default-chat-model-moves-to-sonnet-4-6.md) | The default chat model moves from Sonnet 4.5 to Sonnet 4.6, and the Sonnet 4.6 end-of-life date is unconfirmed | Accepted |

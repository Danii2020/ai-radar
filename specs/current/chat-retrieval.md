# Chat Retrieval Specification

> Last synced: 2026-10-18. Owned artifacts: `src/shared/embeddings.py`,
> `src/shared/retrieval.py`, `src/shared/chat.py`, `src/chat/` (`config.py`,
> `retriever.py`), `run_chat.py`. Deployed 2026-10-18: the backfill ran against the live
> table (16 of 16 cards embedded), and the chat agent reads it through `DynamoCardRetriever`
> (see `chat-agent`). The local `run_chat.py` path is not run live.

## Purpose

The retrieval half of Phase 3: the stored, curated-card vectors that Plane B ranks
against a question, and the switch that lets the local RAG chat read them from
DynamoDB. Its own capability because the retrieval contract (top-k cosine over stored
vectors, the scale ceiling, the no-`Scan` read rule) is the one Plane B depends on,
separate from the Plane A embed step (`curation-pipeline`) and the storage of the
vectors (`card-persistence`). The chat agent, its API and its UI are later specs and
are not described here.

## Requirements

### Requirement: CR-1 — Curated cards carry a stored embedding

The system SHALL, when a curation run persists cards to the DynamoDB card store, write
to every persisted card an `embedding` attribute holding `EMBED_DIM` normalized floats
computed by Titan v2 from `card_text(card)`.

**Source:** chat-retrieval · intent.md § AC1

#### Scenario: A run persists six cards
- **WHEN** a curation run persists 6 cards and Titan succeeds for each
- **THEN** the table holds 6 items, each with a 256-float normalized `embedding`

### Requirement: CR-2 — Embedding never fails a run

The system SHALL treat a Titan failure on one card, or a failed vector write, as a
counted and logged event. The card stays persisted without an `embedding`, the run
completes, and the run status is unchanged.

**Source:** chat-retrieval · intent.md § AC2

#### Scenario: Titan fails on one of six cards
- **WHEN** Titan raises for one card of six
- **THEN** all 6 cards are persisted, 5 carry an embedding, and the embed step's log
  record reports `embed_failed=1`

### Requirement: CR-3 — Vectors are written only by the embedding writer

The system SHALL write `embedding` only through the embedding writer of
`card-persistence` PS-5, never through `upsert`. A re-upsert of an already-embedded card
SHALL leave its stored vector byte-for-byte intact while advancing `updated_at`.

**Source:** chat-retrieval · intent.md § AC3

#### Scenario: Embed a card, then re-upsert it
- **WHEN** a card is embedded and then upserted again
- **THEN** its `embedding` is unchanged and its `updated_at` has advanced

### Requirement: CR-4 — Idempotent backfill

The system SHALL provide a backfill that embeds every card with no `EMBED_DIM`-long
embedding and reports `embedded`, `skipped` and `failed` counts. One card's failure SHALL
NOT stop the rest. A second run SHALL embed zero cards.

**Source:** chat-retrieval · intent.md § AC4

#### Scenario: Backfill over 40 cards, 12 without vectors
- **WHEN** the backfill runs over 40 cards with 12 lacking vectors
- **THEN** it reports `embedded=12 skipped=28 failed=0`, and a second run reports
  `embedded=0 skipped=40 failed=0`

### Requirement: CR-5 — Top-k cosine retrieval over stored vectors

The Plane B retriever's `search(query, k)` SHALL return up to `k` `(card_dict, score)`
pairs, highest cosine first, in the shape of Phase 0's `CardIndex.search`. It SHALL
exclude cards with no usable embedding, SHALL return every embedded card when `k`
exceeds the corpus, SHALL return `[]` for an empty or fully un-embedded corpus, and SHALL
omit the vector from every returned card dict.

**Source:** chat-retrieval · intent.md § AC5

#### Scenario: Retrieve the top four for a question
- **WHEN** `search("open-weight coding models", 4)` runs over an embedded corpus
- **THEN** it returns 4 pairs, scores in descending order, and no card dict containing
  a vector

### Requirement: CR-6 — Corpus read by Query on feed-by-score, never Scan

The retriever SHALL read the corpus with `Query` on the `feed-by-score` index, partition
`CARD`, paginating on `LastEvaluatedKey` until exhausted. It SHALL NOT call `Scan`.

**Source:** chat-retrieval · intent.md § AC6

#### Scenario: The corpus spans two result pages
- **WHEN** the corpus needs two `Query` pages
- **THEN** cards from both pages are candidates for retrieval

### Requirement: CR-7 — Backend switch in run_chat, default unchanged

`run_chat.py` SHALL answer from `DynamoCardRetriever` when `CARD_STORE_BACKEND=dynamo`.
With the default backend it SHALL use the Phase 0 path, a `CardIndex` built over the
local cards, unchanged.

**Source:** chat-retrieval · intent.md § AC7

#### Scenario: Default backend
- **WHEN** `run_chat.py` runs without `CARD_STORE_BACKEND` set
- **THEN** it builds `CardIndex` from the local cards, as in Phase 0

### Requirement: CR-8 — Feed contract and shared types unchanged

The feed response (`CardOut`, `FeedResponse` and their JSON Schema artifact) SHALL NOT
change and SHALL NOT carry `embedding`. The `Card` dataclass, the `CardStore` Protocol,
`RunSummary` and the EMF metrics SHALL NOT change.

**Source:** chat-retrieval · intent.md § AC8

#### Scenario: A feed response for a card that has a vector
- **WHEN** `GET /v1/cards` returns a card that has a stored `embedding`
- **THEN** the response contains no `embedding` key

### Requirement: CR-9 — Planes stay separate

`src/chat/` SHALL import only `shared` and its own modules. `curation`, `shared` and `api`
SHALL NOT import `chat`. `run_chat.py` SHALL import nothing from `curation`. The
plane-separation and constant-equality guards SHALL run in the test suite.

**Source:** chat-retrieval · execution-plan.md § Binding constraints

#### Scenario: A new import crosses the boundary
- **WHEN** a module in `src/chat/` imports `curation` or `api`, or `run_chat.py` imports
  `curation`
- **THEN** the AST guard in `tests/test_chat_contract.py` fails

## Invariants

1. A stored vector is usable only if its length equals `EMBED_DIM`. Any other length
   counts as un-embedded, so a future dimension change heals through the backfill.
2. Retrieval reads only the card partition of `feed-by-score`. A `Scan` would widen the
   read and is forbidden (CR-6).
3. Retrieval is brute force by decision (ADR 0009). It is to be revisited at about 2,000
   embedded cards, or when a measured p95 retrieval latency rises above about 1 s.

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| F7 | Not verified in CI or live. The branch is unpushed, so no `harny-feedback.yml` run exists, and there is no evidence that the Stop hook fired. AC7 is verified offline only: no live `run_chat.py` run against real DynamoDB and Bedrock. | LOW | `specs/archived/chat-retrieval/audit.md` (F7, Final verdict) |
| CAR-F11 | Retrieval latency and the ADR 0009 ceiling have one measured sample: `retrieval_ms=330` on one live chat turn, against 16 live cards. There is no p95, so the scale ceiling is unmeasured. Accepted by the human on 2026-10-18. | LOW | `specs/archived/chat-agent-runtime/audit.md` (F11, AC10 step 8) |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| chat-retrieval | 2026-10-13 | Curation-time embeddings and the sanctioned embedding writer (CR-1..3, PS-5 in `card-persistence`), the backfill (CR-4), `DynamoCardRetriever` with paginated `Query` (CR-5, CR-6), the `RagChat(retriever, k)` seam and the `CARD_STORE_BACKEND` switch (CR-7), the feed-contract guard (CR-8) and the plane-separation guard (CR-9). Not deployed at ship time. |
| chat-agent-runtime | 2026-10-18 | No requirement change. The chat agent consumes CR-5..CR-7 unchanged: `DynamoCardRetriever` for retrieval, and `RagChat` calling the same `answer_question()` step that the agent uses. The 2026-10-18 deploy ran the backfill (CR-4) against the live table, 16 of 16 cards embedded. |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0009](../archived/chat-retrieval/decisions/0009-brute-force-card-retrieval-with-a-scale-ceiling.md) | Brute-force card retrieval over DynamoDB, with a recorded scale ceiling | Accepted |
| [0012](../archived/chat-retrieval/decisions/0012-shared-embeddings-module.md) | The Titan embedding call and card text live in a neutral shared module | Accepted |
| [0013](../archived/chat-retrieval/decisions/0013-plane-b-duplicates-plane-a-constants.md) | Plane B duplicates Plane A's table, index and store constants instead of importing them | Accepted |

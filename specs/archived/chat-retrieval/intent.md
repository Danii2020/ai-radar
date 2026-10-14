# Intent: chat-retrieval

Shipped: 2026-10-13

Revision: 1
Approval: Approved revision 1 by Daniel Erazo on 2026-10-12

## Outcome
Every curated card carries a Titan v2 embedding in the DynamoDB `embedding`
attribute that `dynamodb-card-store` reserved for this: new cards get one at
curation time, and a backfill command fills in the cards that already exist.
Plane B gains a retriever that ranks those stored vectors against a question
by brute-force cosine and returns the top-k cards, with no vector database and
no new always-on cost. This is the retrieval half of Phase 3. The chat agent,
its API and its UI are later specs, and nothing here is deployed.

## Acceptance criteria
- **AC1** After a curation run, every card persisted in that run has an
  `embedding` attribute holding `EMBED_DIM` normalized floats, embedded from
  the card's title, summary, takeaways and tags (the same text Phase 0's
  `_card_text` uses).
  Example: a run that persists 6 cards -> 6 items with a 256-float
  `embedding` in `ai-radar-cards`.
- **AC2** Embedding never fails a curation run. If Titan raises for a card,
  that card is still persisted (without an `embedding`), the run still
  completes, and the failure is counted in the embed step's structured log
  record.
  Example: Titan throws on 1 of 6 cards -> 6 cards persisted, 5 embedded,
  `embed_failed=1` logged, run status unchanged.
- **AC3** `upsert` still never writes `embedding` (PS-2 stands), and a
  re-upsert of an already-embedded card leaves its vector byte-for-byte
  intact.
  Example: embed card X, upsert X again -> X's `embedding` unchanged,
  `updated_at` advanced.
- **AC4** A backfill command embeds every card that has no `embedding` (or
  one whose length is not `EMBED_DIM`) and reports how many it embedded,
  skipped and failed. It is idempotent, and one card's failure does not
  stop the rest.
  Example: 40 cards, 12 without vectors -> `embedded=12 skipped=28
  failed=0`; running it again -> `embedded=0 skipped=40 failed=0`.
- **AC5** The Plane B retriever's `search(query, k)` returns the `k` stored
  cards most similar to the query, highest cosine first, as
  `(card_dict, score)` pairs in the shape Phase 0's `CardIndex.search`
  returns. Cards with no usable embedding are excluded. `k` larger than the
  corpus returns all embedded cards. An empty or fully un-embedded corpus
  returns `[]`.
  Example: `search("open-weight coding models", 4)` -> 4 pairs, scores
  descending, no card dict containing a vector.
- **AC6** The retriever reads the corpus through DynamoDB `Query` on the
  `feed-by-score` index (paginating to exhaustion), never `Scan`. Retrieval
  over a corpus spanning more than one 1 MB result page still considers
  every embedded card.
  Example: a corpus that needs 2 `Query` pages -> cards from both pages
  are candidates.
- **AC7** Running `uv run run_chat.py` with `CARD_STORE_BACKEND=dynamo`
  answers from DynamoDB-retrieved cards with `[n]` citations; with the
  default backend the Phase 0 behavior (local `cards.json` + in-memory
  `CardIndex`) is unchanged.
- **AC8** (compatibility) `GET /v1/cards` responses, the `CardOut` /
  `FeedResponse` contract and its JSON Schema artifact are unchanged, and
  `embedding` never appears in a feed response. The `Card` dataclass, the
  `CardStore` Protocol, `RunSummary` and the EMF metrics are unchanged.
- **AC9** (compatibility) The existing suite (`uv run pytest tests/`, 349
  tests at last count) passes, with only tests whose subject this spec
  deliberately changes updated, and ruff and mypy stay clean.

## Scope
**In**
- A shared embedding helper both planes use (Titan call plus the
  card-to-text rule), so Plane A and Plane B never import each other.
- A curation-time embed step that runs after `persist` and writes vectors
  without going through `upsert`.
- An idempotent backfill command in the style of `run_curation.py` and
  `run_chat.py`.
- A Plane B DynamoDB retriever, and the small change that lets `RagChat`
  use it.
- The `run_chat.py` DynamoDB switch (AC7).
- The runtime execution role gaining `bedrock:InvokeModel` on the Titan v2
  foundation model. The retriever's `dynamodb:Query` grant belongs to the
  later chat-runtime spec that deploys it. Infra tests are updated; nothing
  is deployed.

**Out**
- The chat agent on AgentCore Runtime, the chat API, the web chat UI
  (later Phase 3 specs).
- AgentCore Memory, auth, rate limiting and personalization.
- Any real vector store (pgvector, Pinecone, OpenSearch, ANN indexes).
- Deploying anything, including the agent image rebuild the new embed step
  needs.
- Changes to `RunSummary`, EMF metrics or the budget stack.
- Re-ranking, hybrid or keyword search, and query rewriting.

## Constraints
- `docs/architecture-principles.md` applies: Plane A and Plane B never
  import each other's internals, `Card` is the only shared contract, no
  speculative interfaces. A `Protocol` is allowed only where a second
  implementation exists, which retrieval now has (local `CardIndex` and the
  DynamoDB retriever).
- The curation graph stays portable: `boto3` stays confined to
  `curation/dynamo.py` (card-persistence invariant 1), and the compiled
  graph never imports it.
- Brute force is the deliberate choice (design §7: roughly $0, no
  OpenSearch or Bedrock KB). The spec must record the corpus size or
  latency at which it should be revisited, so that is a decision on file,
  not an accident.
- Vectors come from `EMBED_MODEL_ID` / `EMBED_DIM` with `normalize=True`,
  so cosine equals dot product. A card whose stored length differs from
  `EMBED_DIM` counts as un-embedded (this makes a future dimension change
  self-healing via backfill).
- New env knobs, if any, follow the `pydantic-settings` pattern in
  `config-loading` (typed, fail-fast at import).
- The Docker-image packaging gotcha in `CLAUDE.md` applies to anything
  built into an image: dependency-group membership must be proven by
  building the image, not by `pytest` alone. This spec adds no image, but
  it changes what the existing curation image imports (`shared.*`), so the
  runtime image's closure must be re-checked.
- This spec amends `card-persistence` (PS-2's "never write `embedding`"
  now has a sanctioned separate writer) and `curation-pipeline` (a new
  post-persist step). It does not contradict either: `upsert` is
  unchanged.

## Open questions
- None.

## Revision history
- Revision 1 (2026-10-12): initial draft.

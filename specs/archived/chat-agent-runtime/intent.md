# Intent: chat-agent-runtime

Shipped: 2026-10-18

Revision: 3
Approval: Approved revision 3 by Daniel Erazo on 2026-10-14

## Outcome
The RAG chat from `chat-retrieval` runs as its own agent on Amazon Bedrock
AgentCore Runtime. A caller invokes it with a question and the earlier turns
of the conversation, and gets back a grounded answer with `[n]` citations plus
the cards those citations point to. The agent is stateless: the caller holds
the history. It answers with Claude Sonnet 4.6, the chat model the design
targeted, which the account can now call (the current default, Sonnet 4.5, is
already `LEGACY` in Bedrock). This spec also stands the agent up for real in
AWS, because the whole Phase 3 deploy was staged to start mid-week, and it
carries the `chat-retrieval` deploy steps that the live retrieval depends on.
The chat API (throttling, public URL) and the web chat UI are later specs.

## Acceptance criteria
- **AC1** The chat agent answers one turn. Invoked with `{"question": ...,
  "history": [...]}`, it retrieves the top-k cards for the question, asks
  Sonnet 4.6 to answer only from them, and returns `{"answer": str,
  "sources": [...]}`. Each source carries its citation number `n` (matching
  the `[n]` in the answer), `title`, `url`, `source`, `published` and
  `score`, and never a vector. No other field, such as a `request_id`, is
  returned.
  Example: `{"question": "What shipped in open-weight coding models?",
  "history": []}` -> an answer citing `[1]`, `[2]`, and 4 sources numbered 1-4.
- **AC2** The agent is stateless. Prior turns arrive in `history` as ordered
  `{"role": "user" | "assistant", "text": str}` items, and nothing from one
  invocation survives into the next. The same question with the same history
  is answered from the same inputs regardless of what the process served
  before.
  Example: invoke turn 2 with turn 1's question and answer in `history` -> a
  follow-up such as "and the second one?" resolves against that history.
- **AC3** The request is validated and capped before any model or database
  call. A missing or empty `question`, a `question` over 1,000 characters, a
  `history` that is not a list of well-formed items, more than 10 turns, or
  any single history item over 4,000 characters returns
  `{"error": "invalid_request", "detail": "<which rule>"}` and makes no
  Bedrock or DynamoDB call.
  Example: `{"question": ""}` -> `invalid_request`, zero model calls.
- **AC4** Grounding holds, including when nothing is retrieved. With an empty
  or fully un-embedded corpus the agent still answers, says the context does
  not contain the answer, returns `sources: []` and invents no citation.
  Example: empty table -> a plain "not in the collected news" answer,
  `sources == []`.
- **AC5** Failures never become an unhandled 5xx. A Bedrock or DynamoDB error
  during a turn is logged with a stack trace and returned as
  `{"error": "upstream_failure"}`. The process keeps serving the next
  invocation.
  Example: the model call throws -> `{"error": "upstream_failure"}`, and the
  next valid invocation succeeds.
- **AC6** Each turn writes one structured CloudWatch log record (`chat_turn`)
  with the question length, history length, hits returned, retrieval
  latency, model latency and outcome. It contains neither the question text
  nor the answer text.
  Example: a normal turn -> one `chat_turn` record, `outcome="ok"`, no
  `question` key.
- **AC7** The chat agent has its own least-privilege execution role in its own
  CDK stack. It grants exactly: `bedrock:InvokeModel` on the Sonnet 4.6
  inference profile and its foundation-model ARNs (one per region the profile
  routes to) and on the Titan v2 foundation-model ARN, `dynamodb:Query` on
  the `feed-by-score` index only (no table-level grant, no write action), the
  AgentCore log writes, and ECR pull. It is assumable only by
  `bedrock-agentcore.amazonaws.com` under the `aws:SourceAccount` /
  `aws:SourceArn` conditions. The curation role is not widened for chat.
  Example: the synthesized chat-role policy contains no `dynamodb:Scan`, no
  write action, no Haiku ARN, and no `Resource: "*"` except
  `ecr:GetAuthorizationToken`.
- **AC8** The agent ships as its own container image, built for ARM64 and
  deployed as a second AgentCore Runtime beside the curation agent. Building
  the image and importing the chat entrypoint inside it succeeds, which proves
  the dependency closure rather than relying on `pytest`.
  Example: `docker build` of the chat image, then `python -c "import chat_app"`
  inside it -> exit 0.
- **AC9** The chat model moves to Sonnet 4.6. The default `SONNET_MODEL_ID`
  becomes `us.anthropic.claude-sonnet-4-6`, so the agent and `run_chat.py`
  both answer on it. The summarize-and-tag model (Haiku 4.5), the curation
  role's Haiku statement and the curation graph are not touched.
  Example: `SONNET_MODEL_ID` unset -> `us.anthropic.claude-sonnet-4-6`; a
  `HAIKU_MODEL_ID` default of `us.anthropic.claude-haiku-4-5-20251001-v1:0`.
- **AC10** Live verification in AWS account `626259825216` (human-run, each
  step approved before it runs). In order:
  1. a live smoke call on Sonnet 4.6 with the same request shape the code
     sends (system prompt with a `cachePoint`, `temperature`) is accepted;
  2. redeploy `AiRadarRuntimeRole` for the Titan grant;
  3. rebuild and redeploy the curation agent image, then run one curation
     pass and confirm the cards embed;
  4. run `run_backfill_embeddings.py` once against the live table;
  5. deploy the chat role stack and the chat agent;
  6. invoke the chat agent with a real question and get a cited answer whose
     sources are real cards from the live table;
  7. invoke it with an invalid request and get `invalid_request`;
  8. record the measured retrieval latency and the live card count against
     the ADR 0009 revisit ceiling (about 2,000 cards or p95 above about 1 s).
  Example: step 6 -> an answer with `[1]`, `[2]` and sources whose URLs exist
  in `ai-radar-cards`.
- **AC11** (compatibility) Nothing else changes behavior. `GET /v1/cards`
  and its contract, the `Card` dataclass, the `CardStore` Protocol,
  `RunSummary`, the EMF metrics, the curation graph and the curation
  entrypoint are unchanged. `run_chat.py` keeps working on both backends.
- **AC12** (compatibility) The existing suite (`uv run pytest tests/`, 406
  tests at last count) passes, with only tests whose subject this spec
  deliberately changes updated (the default chat model ID), and ruff and
  mypy stay clean, including under `ruff check --isolated`, which is what CI
  applies.

## Scope
**In**
- A chat entrypoint for AgentCore Runtime, a LangGraph graph of retrieve then
  answer (portable, infra-free), and the request, response and cap rules in
  AC1-AC6.
- The pure turn logic reused from the Phase 0 chat (prompt, context block,
  model call, `[n]` numbering) without carrying per-instance history into a
  stateless agent.
- The default chat model move to Sonnet 4.6 (AC9): the config default, the
  tests that pin the old ID, and the model table in `CLAUDE.md`.
- A chat execution role (CDK construct plus stack), a chat image (separate
  Dockerfile and build context rules), and the infra tests for both.
- The staged deploy and live verification in AC10, including the pending
  `chat-retrieval` deploy steps, and a runbook for them in the README.
- Docs: the README Phase 3 section, `CLAUDE.md`, the architecture doc and the
  changelog.

**Out**
- The chat API, public URL, throttling and CORS (`chat-api`), and the web
  chat UI (`web-chat-ui`).
- Streaming responses (the response is one complete JSON object).
- AgentCore Memory, auth and Cognito, per-user personalization, rate
  limiting.
- Any retrieval change: no cache, no real vector store. The measurement in
  AC10 informs a later decision, it does not trigger one here.
- Changing the summarize-and-tag model or its IAM grant (Haiku 4.5 stays),
  re-ranking, query rewriting, tool use by the model.
- Tearing down, scheduling or enabling anything. The curation schedule stays
  `DISABLED`.

## Constraints
- `docs/architecture-principles.md` applies. The chat agent lives in Plane B:
  `src/chat/` imports only `shared` and its own modules, and `curation`,
  `shared` and `api` never import `chat`. The graph is plain Python plus
  LangGraph with no `bedrock_agentcore` import, which stays in the entrypoint
  file at the repo root (the `runtime-deployment` invariant 1, applied to the
  second agent). No speculative interfaces: the existing `Retriever` Protocol
  is reused, nothing new is added.
- The request caps in AC3 are pinned in config as typed, fail-fast
  pydantic-settings fields (`config-loading`), with those defaults.
- The Docker-image packaging gotcha in `CLAUDE.md` applies. The chat image
  has its own closure, so AC8's in-image import check is mandatory.
- Region `us-east-1`, account `626259825216`. The chat model is called through
  the cross-region profile `us.anthropic.claude-sonnet-4-6`. Titan v2 is
  called by plain model ID.
- Sonnet 4.6 lifecycle (checked 2026-10-14): Bedrock reports it `ACTIVE` with
  no end-of-life date, and a third-party tracker puts Anthropic's own
  retirement at "not sooner than" 2027-02-17, which I could not confirm
  against Anthropic's page. The model ID stays a config knob so a move later
  is an environment change, not a code change. Sonnet 4.5, today's default,
  is already `LEGACY` in Bedrock.
- `agentcore destroy` deletes any role in its config's `execution_role`,
  including a CDK-owned one. The runbook must carry the existing gotcha.
- Cost discipline: the agent adds no always-on cost. An idle AgentCore Runtime
  bills per use. Live verification is a handful of invocations plus one
  curation pass.
- Deploying, the live backfill and the live curation pass write to the real
  account, so each AC10 step waits for the human's explicit go-ahead. No
  executor or auditor runs them unprompted.
- This spec amends `runtime-deployment` (a second agent and its role) and
  builds on `chat-retrieval` (CR-5..CR-7, CR-9). It contradicts neither.

## Open questions
- Does Sonnet 4.6 accept everything the chat call sends, notably the system
  prompt `cachePoint`? Access works (a plain call succeeded on 2026-10-14),
  but the cached request shape is only proven by AC10 step 1, so a rejection
  is treated as a finding to fix, not an assumption.

## Revision history
- Revision 1 (2026-10-14): initial draft.
- Revision 2 (2026-10-14): chat model changed to Haiku 5.5 and curation
  summarize-and-tag moved with it. Superseded by revision 3 before approval.
- Revision 3 (2026-10-14): back to Sonnet 4.6 after checking its lifecycle
  (Bedrock `ACTIVE`, no end-of-life date; access now works in the account);
  the curation model move and the Haiku 5.5 access precondition are dropped;
  `request_id` decided against (AC1); request caps confirmed as proposed;
  new AC9 moves the default chat model off the `LEGACY` Sonnet 4.5.

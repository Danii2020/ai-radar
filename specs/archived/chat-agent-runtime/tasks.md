# Tasks: chat-agent-runtime

## Legend
- [ ] Not started
- [x] Completed
- [~] In progress
- [!] Blocked

Execution plan approved 2026-10-18. Offline work (Phases 1-6) is executor work.
Phase 7 (AC10) writes to the real AWS account `626259825216`: **each step runs
only on the human's explicit go-ahead**, one at a time, and no role runs it
unprompted. Evidence per step (command, output, timestamp, account and table
printed first) is recorded here.

## Phase 0: Red-phase tests (test-writer, before any implementation)
Red-phase evidence: the original red output was not captured at the time. Fresh 2026-10-18 evidence that the tests detect missing behavior (mutations on a scratch copy, never the working tree): removing the `role != _ROLES[i % 2]` check in `src/chat/request.py` makes `tests/test_chat_request.py` fail 2 tests (`test_role_alternation_is_enforced_even_when_the_history_ends_with_assistant[*]`, 2 failed / 29 passed); reverting the retriever's `region_name` makes `tests/test_chat_retriever.py::test_dynamo_resource_is_bound_to_the_shared_region_without_env` fail (1 failed / 10 passed). The audit's 10 other behavior mutations were all caught (audit.md, "Red evidence").
- [x] Task 0.1: `tests/test_chat_request.py` — AC3 validation rules and boundaries (1,000 ok / 1,001 rejected, >20 items, bad roles, non-alternating, not ending with assistant, empty/over-long item text) — `tests/`
- [x] Task 0.2: `tests/test_chat_graph.py` — AC1 shape and numbering, AC2 history mapping/statelessness, AC4 no-context path (zero `converse` calls) plus moto empty and un-embedded table — `tests/`
- [x] Task 0.3: `tests/test_chat_app.py` — AC1/AC3/AC5/AC6 at the entrypoint: `invalid_request` makes no seam calls, `upstream_failure` then recovery, one `chat_turn` record per path with no question/history/answer text — `tests/`
- [x] Task 0.4: `tests/test_infra_chat_runtime.py` — AC7 exact statements, trust conditions, no `Scan`/write/table ARN/Haiku/secret, curation role unchanged — `tests/`
- [x] Task 0.5: extend `tests/test_dockerfile.py` (CMD honors `AGENT_ENTRYPOINT`, default `runtime_app.py`) and `tests/test_chat_contract.py` (import-confinement and no-boto3-client guards) — `tests/`
- [x] Task 0.6: update `tests/test_config.py` to the Sonnet 4.6 default (AC9) and fix the isolated-ruff `tomllib` import-order finding — `tests/test_config.py`

## Phase 1: Model default (AC9)
- [x] Task 1.1: `SONNET_MODEL_ID` default -> `us.anthropic.claude-sonnet-4-6`, correct its comment — `src/shared/config.py`
- [x] Task 1.2: update `.env.example` to match — `.env.example`

## Phase 2: Shared stateless answer step (AC2, AC11)
- [x] Task 2.1: extract a public answer function (question, prior Converse messages, hits -> text) from `RagChat.ask`; `RagChat.ask` calls it and keeps its own `self.history` — `src/shared/chat.py`
- [x] Task 2.2: confirm `tests/test_rag_chat.py` stays green untouched — `tests/`

## Phase 3: Plane B logic (AC1-AC4)
- [x] Task 3.1: add `CHAT_MAX_QUESTION_CHARS` (1000), `CHAT_MAX_HISTORY_TURNS` (10), `CHAT_MAX_HISTORY_ITEM_CHARS` (4000) as typed pydantic-settings fields with explicit `validation_alias` — `src/chat/config.py`
- [x] Task 3.2: `parse_request` (pure; `detail` is a rule name, never an echo of input) — `src/chat/request.py`
- [x] Task 3.3: `build_chat_graph(retriever, k)` — `retrieve` then `answer`; no-hits returns the fixed message with no model call; sources builder `{n,title,url,source,published,score}` (score rounded to 4) — `src/chat/graph.py`

## Phase 4: Composition root (AC1, AC3, AC5, AC6)
- [x] Task 4.1: `chat_app.py` — sync `@app.entrypoint` handler: `parse_request` -> graph -> `{answer, sources}`; `logger.exception` + `upstream_failure`; graph and `DynamoCardRetriever` built once at import; only file importing `bedrock_agentcore` for chat — `chat_app.py`
- [x] Task 4.2: one `chat_turn` record per invocation via child logger `bedrock_agentcore.app.chat` with the pinned keys and outcomes — `chat_app.py`

## Phase 5: Infra (AC7)
- [x] Task 5.1: `ChatRuntime` construct (role only, pinned statements) — `infra/lib/chat_runtime.py`
- [x] Task 5.2: `AiRadarChatRuntime` stack with `ExecutionRoleArn` output; register in `infra/app.py` — `infra/stacks/chat_runtime_stack.py`, `infra/app.py`

## Phase 6: Packaging (AC8)
- [x] Task 6.1: root `Dockerfile` CMD selects entrypoint via `AGENT_ENTRYPOINT` (default `runtime_app.py`); adjust `.dockerignore` only if needed — `Dockerfile`
- [x] Task 6.2: build ARM64 image and run `python -c "import chat_app"` inside it; remove the probe image (needs local Docker daemon)
  - Evidence (2026-10-18, fresh run after F4): `docker build --platform linux/arm64 -t ai-radar-chat-probe:f4 .` built (only a lint warning on the `FROM --platform` constant); `docker run --rm --platform linux/arm64 --entrypoint python ai-radar-chat-probe:f4 -c "import chat_app; print('import ok')"` printed `import ok` with NO `AWS_DEFAULT_REGION` (image env has no `AWS*` vars). Probe image removed with `docker rmi`.
- [x] Task 6.3: README Phase 3 AC10 runbook (flags in the commands, `-a <agent>`, `default_agent` note, `agentcore destroy` role gotcha) and optional invoke-only `run_chat_agent_smoke.py` — `README.md`
- [x] Task 6.4: full gate: `uv run pytest tests/ && uv run ruff check && uv run ruff check --isolated && uv run mypy .` (AC11, AC12)
  - Evidence (2026-10-18, after F1-F4): `uv run pytest tests/` -> 487 passed; `uv run ruff check` -> All checks passed; `uv run ruff check --isolated` -> All checks passed; `uv run mypy .` -> Success: no issues found in 87 source files. (One I001 import-order finding in the new `tests/test_chat_request.py` was fixed with `ruff --fix` and the two ruff runs repeated clean.)

## Audit finding responses (round 1, 2026-10-18)
- F1: added `test_role_alternation_is_enforced_even_when_the_history_ends_with_assistant` (`[assistant]`, `[user,assistant,assistant]`, both end with assistant so only alternation rejects them; asserts detail `history_roles_not_alternating`). Fails with the check removed (scratch copy), passes in the tree.
- F2: README AC10 step 1 is now `aws sts get-caller-identity && PYTHONPATH=src uv run python -c ...`. Offline `PYTHONPATH=src uv run python -c "from shared.chat import answer_question"` imports fine (no Bedrock call made).
- F3: evidence recorded under 6.2, 6.4 and Phase 0 above.
- F4: `chat.retriever._dynamo_resource` passes `region_name=shared.config.AWS_REGION`; test added; docker import probe passes with no region env (see 6.2).
- F5-F8 untouched (not in the approved scope).

## Phase 7: Live verification (AC10, human-gated, one step at a time)
- [x] Task 7.1: smoke call on Sonnet 4.6 with the real request shape (`cachePoint` + `temperature`)
      Evidence (2026-10-18T22:42Z, human-approved);
      README step 1 command with `SONNET_MODEL_ID=us.anthropic.claude-sonnet-4-6`, printed
      `model: us.anthropic.claude-sonnet-4-6`; Bedrock accepted the request (system prompt
      `cachePoint` + `temperature`) and returned a normal answer. Open question closed: no rejection.
- [x] Task 7.2: redeploy `AiRadarRuntimeRole` (Titan grant)
      Evidence (2026-10-18, human-run): account `626259825216`; `cdk diff` showed one added statement
      (`InvokeTitanEmbed`, `bedrock:InvokeModel` on the Titan v2 foundation-model ARN) and nothing else;
      `cdk deploy ... --require-approval never` -> `UPDATE_COMPLETE` (23.6 s); `aws iam get-role-policy`
      on the execution role shows the live `InvokeTitanEmbed` statement. (A first `!` run without
      `--require-approval never` only created a change set, as no TTY was attached; nothing applied.)
- [x] Task 7.3: rebuild/redeploy curation image; one curation pass; confirm cards embed
      Evidence (2026-10-18, human-approved each step; account `626259825216`, table `ai-radar-cards`):
      before: 8 cards; `uv run agentcore deploy -a ai_radar_curation --auto-update-on-conflict` ->
      deployed, Last Updated 2026-10-18 22:51 UTC; `agentcore invoke` -> `accepted`, run_id
      `a6168787ff1c4165a223d4e6ef26c91c`; `curation_run_complete`: discovered 40, summarized 8,
      persisted 8, store_failures 0, 30.6 s, est. cost $0.06; `embed_complete`: embedded 8,
      embed_failed 0. After: 16 cards total, 8 with an `embedding` attribute (the 8 old cards
      await step 4's backfill).
- [x] Task 7.4: `run_backfill_embeddings.py` once against the live table
      Evidence (2026-10-18T22:54Z, human-approved): printed `account=626259825216 table=ai-radar-cards`;
      first run `embedded=8 skipped=8 failed=0`; second run `embedded=0 skipped=16 failed=0`
      (idempotent); scan shows 16 of 16 cards with an `embedding` attribute.
- [x] Task 7.5: deploy `AiRadarChatRuntime` and the chat agent with `--env AGENT_ENTRYPOINT=chat_app.py`
      Evidence (2026-10-18, human-approved; account `626259825216`): `cdk diff` showed a new role +
      policy only (7 statements as AC7); `cdk deploy AiRadarChatRuntime` -> `CREATE_COMPLETE` (39 s),
      ExecutionRoleArn `...AiRadarChatRuntime-ChatRuntimeExecutionRole68B5D130-4yZyw5ZczsyQ`;
      `agentcore configure --create -n ai_radar_chat -e chat_app.py ...` (default_agent flipped to
      `ai_radar_chat`; curation config intact; all later commands pass `-a`);
      `agentcore deploy -a ai_radar_chat --env AGENT_ENTRYPOINT=chat_app.py` -> runtime
      `ai_radar_chat-JFCO0R9lkT` deployed. That the chat entrypoint (not curation) is running is
      proven by step 7.6.
- [x] Task 7.6: invoke with a real question; cited answer, sources exist in `ai-radar-cards`
      Evidence (2026-10-18T22:58Z, human-approved; account `626259825216`):
      `agentcore invoke -a ai_radar_chat '{"question": "What are the latest developments in open-weight
      models?", "history": []}'` -> grounded answer citing [1]-[3] with 4 sources numbered 1-4
      (`n,title,url,source,published,score` only, no vector, no request_id); all 4 source URLs exist in
      `ai-radar-cards` (scan). Confirms the container runs `chat_app.py` (AGENT_ENTRYPOINT took effect).
      `chat_turn` log record: question_chars 55, history_items 0, hits 4, retrieval_ms 330,
      model_ms 3304, outcome ok; no question or answer text in it.
- [x] Task 7.7: invoke with an invalid request; get `invalid_request`
      Evidence (2026-10-18T22:59Z, human-approved): `agentcore invoke -a ai_radar_chat '{"question": ""}'`
      -> `{"error": "invalid_request", "detail": "question_empty"}`; `chat_turn` record: question_chars 0,
      hits 0, retrieval_ms 0, model_ms 0, outcome invalid_request (no retrieval or model call).
- [x] Task 7.8: record retrieval latency and live card count against the ADR 0009 ceiling (~2,000 cards / p95 ~1 s)
      Provisional (2026-10-18): live table 16 cards (all embedded) = 0.8% of the ~2,000-card ceiling;
      one real turn measured retrieval_ms 330 (cold-ish single sample, includes the Titan embed call),
      model_ms 3304. A p95 needs more samples; only one has been taken.
      Closed by the human on this provisional evidence (no extra samples); revisit when the corpus grows.

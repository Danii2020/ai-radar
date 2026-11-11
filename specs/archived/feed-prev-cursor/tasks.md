# Tasks: feed-prev-cursor

## Status
Approved, implemented (O1-O6) and audited (round 1: approved with reservations). O7 done; O8 (PR, deploy, live runbook) is human-only and pending.

## Baseline
- Base commit: c9c0c2f (`main`)
- Branch: `feat/feed-prev-cursor` (to create from `main`. Do not work on `main`, because CI deploys from it)
- Interpreter: Python 3.12.11 (`uv run python --version`)
- Cwd: `/Users/danielerazo/python/project-agentcore-app` (repo root); `apps/web` for the type regeneration
- Commands: `uv run pytest tests/ -q`; `uv run ruff check .`; `uv run mypy .`; in `apps/web`:
  `npm run generate:types`, `npx vitest run features/feed/api/types.generated.test.ts`, `npm run typecheck`
- Pre-existing failures: none. `uv run pytest tests/ -q` -> 837 passed, 202 warnings (2026-11-10, base
  c9c0c2f, about 175 s on this machine). Ruff, mypy and the `apps/web` checks were not run for the baseline.
- Pre-existing tree state: uncommitted `apps/web` feed changes (components, `api/client.ts`,
  `api/load-feed.ts`, `e2e/feed.e2e.ts`, e2e baselines) and an untracked `.claude/worktrees/`. They are not
  part of this feature. Do not stage, revert or reformat them.

## Outcomes
- [x] **O1** (AC5, AC6): direction-aware cursor in `src/api/cursor.py`. Forward-with-key tokens stay
  byte-identical, and the backward and keyless shapes are exact-match validated.
  - Tests: `tests/test_feed_cursor.py` (new T1, T2; existing tests migrated only at call sites)
  - Red: `uv run pytest tests/test_feed_cursor.py -q` -> T1 and T2 fail
  - Green: `uv run pytest tests/test_feed_cursor.py -q` -> all pass
- [x] **O2** (AC1, AC2, AC3, AC4, AC7): the backward query and the page cursor rules
  (`execution-plan.md` § Binding constraints table) in `src/api/feed.py` and `src/api/handler.py`, and
  `prev_cursor` in every 200 body. One `Query` per request. The backward `Limit` is `limit + 1` (Q1
  option A).
  - Tests: `tests/test_feed_api_handler.py` (new T3, T4)
  - Red: `uv run pytest tests/test_feed_api_handler.py -q` -> T3 and T4 fail
  - Green: `uv run pytest tests/test_feed_api_handler.py tests/test_feed_query.py -q` -> all pass
- [x] **O3** (AC8): contract and generated artifacts. Add `FeedResponse.prev_cursor` and update its
  docstring, run `uv run export_api_schema.py`, then in `apps/web` run `npm run generate:types`. Neither
  generated file is hand-edited. `CARD_SCHEMA_VERSION` stays `"v1"`. Correct the `export_api_schema.py`
  docstring: an added optional field does not bump the version.
  - Tests: existing `tests/test_feed_api_contract.py::test_committed_schema_artifact_matches_contracts_json_schema`,
    `apps/web/features/feed/api/types.generated.test.ts`
  - Red: after the model change and before regeneration, `uv run pytest tests/test_feed_api_contract.py -q`
    -> drift failure
  - Green: `uv run pytest tests/test_feed_api_contract.py tests/test_contracts_card.py -q` and
    (cwd `apps/web`) `npx vitest run features/feed/api/types.generated.test.ts && npm run typecheck` -> pass.
    `git diff --stat -- apps/web` lists only `features/feed/api/types.generated.ts` beyond the pre-existing
    uncommitted files.
- [x] **O4** Migration (AC5, AC7, AC8): update call sites in `tests/test_feed_cursor.py`,
  `tests/test_feed_query.py` and `tests/test_feed_api_handler.py` only where a signature changed. No
  assertion is weakened or removed. `tests/test_infra_feed_api.py` and `infra/` are untouched.
- [x] **O5** Docs: the `FeedResponse` and `export_api_schema.py` docstrings (in O3). `docs/history.md`
  and the `feed-api` capability doc are left to the documentation step, after the live check (O8).
- [x] **O6** Broader suite vs baseline (AC8): `uv run pytest tests/ -q && uv run ruff check . && uv run mypy .`
  -> 837 plus the new tests (each parametrized case counts), all pass, ruff and mypy clean.
- [ ] **O7** Independent audit: verdict from `specs/feed-prev-cursor/audit.md`.
- [ ] **O8** (AC9) Human-only, post-merge, NOT an executor task: open the PR (read the CI `cdk diff`, which
  should show no IAM change for `AiRadarFeedApi`), merge to `main`, wait for the `backend deploy` run that
  deploys `AiRadarFeedApi` and its smoke to pass, then run the live runbook L1 to L6 in
  `execution-plan.md` § Validation and record the output here.

## Working state
- Updated: 2026-11-10
- Outcome: O1-O7 done; O8 pending (human)
- Phase: implemented and audited (round 1, approved with reservations); documentation step and live check remain
- In progress: nothing
- Red run: T1 4 failed (unexpected keyword 'direction'); T3 and T4 3 failed (KeyError 'prev_cursor'); T2 green by design (a permissiveness guard: the old decoder already rejects those shapes)
- Green run: `uv run pytest tests/ -q` -> 849 passed (837 + 12 new cases); `uv run ruff check .` clean; `uv run mypy .` clean; vitest types.generated 3 passed; `npm run typecheck` clean
- Next step: documentation role (README, F1), then the human runs O8 and runbook L1 to L6

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Checkpoint
Specs approved, O1-O6 implemented, audit round 1 approved with reservations (F2 and F6 closed in tests, F3 closed here; F1 left to the documentation role). Resume at O8 (human).

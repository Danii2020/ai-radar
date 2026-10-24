# Tasks: Web Chat UI

## Status
Implementing (spec set approved by Daniel Erazo on 2026-10-22; red-phase tests next)

## Baseline
- Base commit: 48334d8 (`main`). Implement on a new branch, `feat/web-chat-ui`; `main` is the PR base.
- Branch: main
- Interpreter: Node v24.16.0, npm 11.13.0
- Cwd: /Users/danielerazo/python/project-agentcore-app/apps/web
- Commands: test `npm test`; lint `npm run lint`; type-check `npm run typecheck`; build `npm run build`;
  e2e `npm run test:e2e` (offline; needs `npx playwright install chromium` once)
- Pre-existing failures: none. At the base commit, 2026-10-22: `npm test` 10 files, 87 tests passed;
  `npm run typecheck` clean; `npm run lint` 0 errors and 1 warning (an unused `eslint-disable`
  directive). `npm run build` and `npm run test:e2e` not yet run at baseline: record them first.

## Outcomes
Order is TDD: write the red tests for an outcome, then the code. Every outcome keeps `npm run lint`
and `npm run typecheck` clean. The real key is never read, printed or written; tests use fake values.

- [x] **O1** (AC3, AC4): Limits and history rules in `features/chat/lib/`: `limits.ts`
  (`QUESTION_MAX_CHARS` 1000, `HISTORY_MAX_ITEMS` 20, `ITEM_MAX_CHARS` 4000, body cap 524,288 bytes)
  and `history.ts` (shape check, keep-last-20, per-item cut). Add `aws4fetch` at an exact version at
  least two weeks old (`npm view aws4fetch time`), with `package-lock.json`.
  - Tests: `features/chat/lib/history.test.ts`
  - Red: `npx vitest run features/chat/lib/history.test.ts` -> fails (module missing)
  - Red evidence (2026-10-22): features/chat/lib/history.test.ts -> suite fails: Failed to resolve import "./history" (module missing)
  - Green: same command passes; 12 turns -> last 10 forwarded; over-long item cut; invalid shapes rejected
  - Green evidence (2026-10-22): `npx vitest run` -> history.test.ts passes; aws4fetch 1.0.20 (published 2024-08-28) pinned exactly in package.json and package-lock.json
- [x] **O2** (AC5, AC6): `features/chat/api/types.ts` and `backend.ts`: sign with `AwsClient.sign()`
  (`retries: 0`, service `execute-api`, region `us-east-1`), one `fetch` with an abort signal, response
  shape check, status-to-outcome mapping.
  - Tests: `features/chat/api/backend.test.ts`
  - Red: `npx vitest run features/chat/api/backend.test.ts` -> fails (module missing)
  - Red evidence (2026-10-22): features/chat/api/backend.test.ts -> suite fails: Failed to resolve import "./backend" (module missing)
  - Green: same command passes; signed header scope asserted; `fetch` called once on 429, 502, 504 and abort; secret never in the request
  - Green evidence (2026-10-22): backend.test.ts passes (SigV4 scope us-east-1/execute-api, secret absent, fetch once on 429/502/504/abort)
- [x] **O3** (AC3, AC4, AC5, AC6): `features/chat/api/handle-chat-request.ts`: size check, parse,
  validate, trim, read env per request, call backend, map to the fixed codes, one text-free JSON log line.
  - Tests: `features/chat/api/handle-chat-request.test.ts`
  - Red: `npx vitest run features/chat/api/handle-chat-request.test.ts` -> fails (module missing)
  - Red evidence (2026-10-22): features/chat/api/handle-chat-request.test.ts -> suite fails: Failed to resolve import "./handle-chat-request" (module missing)
  - Green: same command passes; every row of the plan's mapping table; no body or log line holds the fake key, secret, base URL, question, history or answer; local failures never call `fetch`
  - Green evidence (2026-10-22): handle-chat-request.test.ts passes (full mapping table, no leaks, one text-free log line)
- [x] **O4** (AC6): `app/api/chat/route.ts`: `runtime = 'nodejs'`, `dynamic = 'force-dynamic'`,
  `maxDuration`, `POST` delegating to `handleChatRequest`; `features/chat/index.ts` barrel exporting
  `ChatWidget` and `handleChatRequest` only.
  - Tests: `features/chat/api/route-config.test.ts` only if it asserts something other than the literals; otherwise covered by O3 and the O7 conventions guard
  - Red: `npx vitest run features/chat` -> barrel and route imports fail
  - Green: `npm run typecheck` clean; `npm run build` lists `/api/chat` as a dynamic route
  - Green evidence (2026-10-22): `npm run typecheck` clean; `npm run build` lists `ƒ /api/chat` as a dynamic route
- [x] **O5** (AC2, AC3, AC5): `features/chat/lib/conversation.ts` (reducer: messages, pending, error,
  retry; history grows by a pair only on success) and `lib/send-turn.ts` (browser `fetch` to
  `/api/chat`, 35 s deadline, response and error-code mapping).
  - Tests: `features/chat/lib/conversation.test.ts`, `features/chat/lib/send-turn.test.ts`
  - Red: `npx vitest run features/chat/lib` -> fails (modules missing)
  - Red evidence (2026-10-22): conversation.test.ts, send-turn.test.ts -> suites fail: Failed to resolve import "./conversation" / "./send-turn" (modules missing)
  - Green: same command passes; a failed turn leaves history unchanged and keeps the question
  - Green evidence (2026-10-22): conversation.test.ts and send-turn.test.ts pass
- [x] **O6** (AC1, AC2, AC4, AC5, AC8): components under `features/chat/components/`: `chat-widget.tsx`,
  `chat-panel.tsx`, `message-list.tsx`, `source-list.tsx`, `chat.module.css` (tokens only, no console
  output). Dialog `div` with `role="dialog"`, focus in and out, Escape, `aria-expanded`, `aria-live`.
  - Tests: `features/chat/components/chat-widget.test.tsx`, `features/chat/components/chat-css.test.ts`
  - Red: `npx vitest run features/chat/components` -> fails (modules missing)
  - Red evidence (2026-10-22): chat-widget.test.tsx fails on missing "./chat-widget"; chat-css.test.ts fails: ENOENT chat.module.css
  - Green: same command passes; one rendered state per error code; source links point at each `url`
  - Green evidence (2026-10-22): chat-widget.test.tsx and chat-css.test.ts pass
- [x] **O7** (AC6, AC7): mount `<ChatWidget />` beside `<FeedView />` in `app/page.tsx`; add
  `features/chat/conventions.test.ts` (layout, barrel exports exactly `ChatWidget` and
  `handleChatRequest`, no deep imports from outside, no barrel self-import, no `"use client"` import
  of the barrel or `api/`, `components/` and `lib/` use `import type` for `api/`, no `.sort(` or
  `.reverse(`); narrow T29 in `features/feed/conventions.test.ts` to the host form and add a case that
  the narrowed pattern still fires on a host literal.
  - Tests: `features/chat/conventions.test.ts`, `features/feed/conventions.test.ts`
  - Red: `npx vitest run features/chat/conventions.test.ts features/feed/conventions.test.ts` -> new guards fail before the code exists
  - Red evidence (2026-10-22): features/chat/conventions.test.ts: 3 cases fail (layout: index.ts missing; barrel: cannot find ./index; app/page.tsx does not import @/features/chat). Feed T29 narrowing and its guard case pass now (the narrowing only becomes necessary once api/backend.ts uses 'execute-api'); feed suite 88 passed
  - Green: same command passes, and the existing feed suite is untouched: `npx vitest run features/feed`
  - Green evidence (2026-10-22): chat and feed conventions tests pass; feed suite untouched; app/page.tsx mounts ChatWidget beside FeedView
- [x] **O8** (AC1, AC2, AC4, AC5, AC6, AC7, AC8, AC9): e2e. Extend `e2e/stub/feed-api-stub.mjs` with
  `POST /<scenario>/v1/chat` (checks the SigV4 `Authorization` scope, answers by question keyword:
  answer with 3 sources, 429, 504, 502, 403). Extend `e2e/stub/launch-apps.mjs` with
  `CHAT_API_BASE_URL` and two obviously fake credential values on both instances. Add
  `e2e/chat.e2e.ts`. Do not edit `e2e/feed.e2e.ts` or anything under `e2e/__baseline__/`.
  - Tests: `e2e/chat.e2e.ts`
  - Red: `npx playwright test e2e/chat.e2e.ts` -> fails (no widget on the page)
  - Red evidence (2026-10-22): e2e/chat.e2e.ts lists 9 tests; `npx playwright test e2e/chat.e2e.ts` cannot start yet: the webServer `next build` fails type-check because the unit tests import modules that do not exist. Becomes red-by-assertion (no widget) once the modules exist
  - Green: same command passes offline; then `npm run test:e2e` passes all 17 baseline scenarios plus the chat ones with no `--update-snapshots`; `git diff --stat -- e2e/__baseline__` is empty
  - Green evidence (2026-10-22): `npm run test:e2e` -> 32 passed (9 chat + 23 feed incl. 17 baseline); `git diff --stat -- e2e/__baseline__` empty; stub and launch-apps unchanged by the executor
- [x] **O9** Migration: `.env.example` (three placeholder names, no real value, no `NEXT_PUBLIC_`);
  confirm no change under `app/globals.css`, `features/feed/components/feed.module.css`, or
  `e2e/__baseline__/`; confirm `features/feed/` source is untouched apart from the T29 pattern.
  - Check: `git diff --stat` lists only the files named in the plan's Ownership section
  - Green evidence (2026-10-22): .env.example has 3 placeholders only; no diff under app/globals.css, feed.module.css, e2e/__baseline__; features/feed diff is only conventions.test.ts (the pre-approved T29 narrowing)
- [x] **O10** Docs: `AGENTS.md` (layout block, import rule, barrel rule, dependency sentence, env note)
  and `README.md` in `apps/web` (local chat setup, the human step of putting the key in `.env.local`,
  the live check). Root `README.md` "Phase 3" notes are handed to the human or `harny-document`.
  - Green evidence (2026-10-22): AGENTS.md (layout, import rule, barrel rule, dependency sentence, env note) and apps/web README.md (Chat widget: local setup) updated
- [x] **O11** Broader suite vs baseline: `npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e`
  -> all green; test count at least the baseline 87 plus the new ones; lint warnings no more than the baseline 1.
  - Green evidence (2026-10-22): lint 0 errors 1 warning (baseline); typecheck clean; npm test 18 files 237 tests passed (baseline 87); build ok; test:e2e 32 passed
- [x] **O12** Independent audit: verdict from `audit.md` (written by the auditor only).
  - Verdict (2026-10-22, round 1): APPROVED WITH RESERVATIONS; no blocking findings (F1, F2 MEDIUM open)

Human tasks (agents stop at local verification, WEB-11; these are not executor outcomes):
- [ ] **H1** (AC6, AC2, WEBCHAT-R2): put the caller key in `apps/web/.env.local` under the three
  `CHAT_API_*` names (read it from the local profile `ai-radar-chat-caller` yourself; never paste it
  into a chat or log), run `npm run dev`, ask one real question, and record the latency and that the
  answer cites `[1]`. Rotation and leak steps are in the root README, "Authentication amendment".
- [ ] **H2** (WEBCHAT-R3): before the Vercel deploy, check the plan's function duration limit against
  `maxDuration`, and set the three `CHAT_API_*` variables in the Vercel project (not `AWS_*`).

## Working state
- Updated: 2026-10-22
- Outcome: O1 to O11 done; O12 (audit) and H1/H2 open
- Phase: implemented, awaiting audit
- In progress: none
- Last command: `npm run test:e2e` -> 32 passed (after lint, typecheck, npm test 237 passed, build)
- Next step: auditor reviews; human does H1 and H2

## Finding responses
| Finding | Response | Evidence |
|---|---|---|

## Checkpoint
Spec set complete: `intent.md` (approved, revision 2), `execution-plan.md` and `tasks.md` (both
awaiting the human's approval). Resume at O1 on branch `feat/web-chat-ui` once approved.
